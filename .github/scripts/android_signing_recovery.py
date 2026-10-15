#!/usr/bin/env python3
"""Encrypt, verify and recover the existing Android release identity."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess  # nosec B404
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "Elegying/Hysteria2-panel"
APPLICATION_ID = "vip.ssrvpn.hysteria2manager"
SECRET_FIELDS = {
    "keystore_base64": "ANDROID_SIGNING_KEYSTORE_BASE64",
    "store_password": "ANDROID_SIGNING_STORE_PASSWORD",
    "key_alias": "ANDROID_SIGNING_KEY_ALIAS",
    "key_password": "ANDROID_SIGNING_KEY_PASSWORD",
}
BACKUP = ROOT / "ops/android-signing/backup.json.age"
WORKFLOW = "android-signing-recovery.yml"


def run(command, payload=None, env=None, timeout=180):
    executable = shutil.which(command[0])
    if executable is None:
        raise RuntimeError("缺少工具：{}".format(command[0]))
    result = subprocess.run(  # nosec B603
        [executable] + command[1:], input=payload, capture_output=True,
        env=env, timeout=timeout, check=False,
    )
    if result.returncode:
        # Tool output can contain credentials; never relay it to logs or chat.
        raise RuntimeError("{} 执行失败；未输出可能包含凭据的诊断".format(command[0]))
    return result.stdout


def expected_certificate():
    workflow = (ROOT / ".github/workflows/android-release.yml").read_text()
    match = re.search(r"^      EXPECTED_CERT_SHA256: ([0-9a-f]{64})$", workflow, re.M)
    if not match:
        raise ValueError("正式发布工作流缺少固定证书指纹")
    return match.group(1)


def recipient_value(value):
    if not re.fullmatch(r"age1[023456789acdefghjklmnpqrstuvwxyz]{58}", value):
        raise ValueError("接收方必须是 age-keygen 生成的 X25519 公钥")
    return value


def bundle_from_environment():
    bundle = {key: os.environ.get(variable, "") for key, variable in SECRET_FIELDS.items()}
    bundle.update(format_version=1, repository=REPOSITORY, application_id=APPLICATION_ID)
    return bundle


def validate_bundle(bundle):
    expected_fields = set(SECRET_FIELDS) | {"format_version", "repository", "application_id"}
    if not isinstance(bundle, dict) or set(bundle) != expected_fields:
        raise ValueError("签名备份字段不符合固定格式")
    if (bundle["format_version"] != 1 or bundle["repository"] != REPOSITORY
            or bundle["application_id"] != APPLICATION_ID):
        raise ValueError("签名备份不属于本项目")
    for field in SECRET_FIELDS:
        value = bundle[field]
        limit = 128 * 1024 if field == "keystore_base64" else 4096
        if not isinstance(value, str) or not value or len(value) > limit or "\0" in value:
            raise ValueError("签名备份缺少有效的 {}".format(field))
    try:
        keystore = base64.b64decode(bundle["keystore_base64"], validate=True)
    except ValueError as exc:
        raise ValueError("密钥库编码无效") from exc
    if not 128 <= len(keystore) <= 96 * 1024:
        raise ValueError("密钥库大小异常")
    return keystore


def write_private(path, data):
    """Create without replacing a different existing file or following symlinks."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("拒绝覆盖符号链接")
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError("目标已有不同内容，已保留原文件：{}".format(path))
        path.chmod(0o600)
        return
    with tempfile.NamedTemporaryFile(dir=str(path.parent), delete=False) as handle:
        temporary = Path(handle.name)
        try:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.link(str(temporary), str(path))
        finally:
            temporary.unlink()


def check_key(bundle):
    keystore = validate_bundle(bundle)
    with tempfile.TemporaryDirectory(prefix="h2-signing-check-") as directory:
        key = Path(directory) / "release.jks"
        write_private(key, keystore)
        env = dict(os.environ)
        env.update(H2_STORE_PASSWORD=bundle["store_password"],
                   H2_KEY_PASSWORD=bundle["key_password"],
                   H2_CHECK_PASSWORD=secrets.token_urlsafe(32))
        certificate = run([
            "keytool", "-exportcert", "-keystore", str(key),
            "-storepass:env", "H2_STORE_PASSWORD", "-alias", bundle["key_alias"],
        ], env=env)
        fingerprint = hashlib.sha256(certificate).hexdigest()
        if fingerprint != expected_certificate():
            raise ValueError("签名证书与正式发布身份不一致，未恢复")
        # Importing the private entry also verifies keyPassword, not only storePassword.
        run([
            "keytool", "-importkeystore", "-noprompt", "-srckeystore", str(key),
            "-srcstorepass:env", "H2_STORE_PASSWORD", "-srckeypass:env", "H2_KEY_PASSWORD",
            "-srcalias", bundle["key_alias"], "-destkeystore", str(Path(directory) / "check.p12"),
            "-deststoretype", "PKCS12", "-deststorepass:env", "H2_CHECK_PASSWORD",
        ], env=env)
    return {"certificate_sha256": fingerprint, "keystore_sha256": hashlib.sha256(keystore).hexdigest()}


def encrypt(bundle, recipient, output):
    recipient_value(recipient)
    check_key(bundle)
    payload = json.dumps(bundle, ensure_ascii=True, sort_keys=True).encode("ascii")
    ciphertext = run(["age", "--encrypt", "--recipient", recipient], payload=payload)
    write_private(output, ciphertext)


def decrypt(backup, identity):
    backup = Path(backup)
    if not backup.is_file() or backup.stat().st_size > 256 * 1024:
        raise ValueError("加密备份不存在或大小异常")
    plaintext = run(["age", "--decrypt", "--identity", str(identity), str(backup)])
    try:
        bundle = json.loads(plaintext)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("解密后的备份格式无效") from exc
    check_key(bundle)
    return bundle


def property_value(value):
    result = []
    for character in str(value):
        if character in "\\=:#! ":
            result.append("\\" + character)
        elif not 33 <= ord(character) <= 126:
            encoded = character.encode("utf-16-be")
            result.extend("\\u" + encoded[index:index + 2].hex() for index in range(0, len(encoded), 2))
        else:
            result.append(character)
    return "".join(result)


def install_bundle(bundle, project_root, signing_directory):
    metadata = check_key(bundle)
    project_root = Path(project_root).resolve()
    android = project_root / "mobile/android"
    if not (android / "signing.properties.example").is_file():
        raise ValueError("目标不是完整的项目源码目录")
    signing_directory = Path(signing_directory).expanduser().resolve()
    signing_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    signing_directory.chmod(0o700)
    key = signing_directory / "hysteria2-manager-release.jks"
    properties = android / "signing.properties"
    values = {"storeFile": str(key), "storePassword": bundle["store_password"],
              "keyAlias": bundle["key_alias"], "keyPassword": bundle["key_password"]}
    content = "".join("{}={}\n".format(k, property_value(v)) for k, v in values.items()).encode("ascii")
    targets = [(key, validate_bundle(bundle)), (properties, content)]
    for path, data in targets:
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_bytes() != data)):
            raise ValueError("目标已有不同内容，已保留原文件：{}".format(path))
    for path, data in targets:
        write_private(path, data)
    if any(stat.S_IMODE(path.stat().st_mode) != 0o600 for path, _ in targets):
        raise ValueError("签名文件权限验证失败")
    print(json.dumps(dict(metadata, signing_properties=str(properties), private_key=str(key)), ensure_ascii=False))


def rewrap_backup(recipient, output):
    digest_file = BACKUP.with_suffix(BACKUP.suffix + ".sha256")
    if not BACKUP.is_file() or not digest_file.is_file():
        raise ValueError("持久加密备份尚未入库，请先完成 export-current 和备份提交")
    digest = digest_file.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(BACKUP.read_bytes()).hexdigest() != digest:
        raise ValueError("加密备份 SHA-256 校验失败")
    identity = os.environ.get("ANDROID_SIGNING_BACKUP_AGE_IDENTITY", "")
    if not identity.startswith("AGE-SECRET-KEY-1") or "\n" in identity.strip():
        raise ValueError("缺少有效的备份恢复密钥 Secret")
    with tempfile.TemporaryDirectory(prefix="h2-signing-rewrap-") as directory:
        identity_file = Path(directory) / "identity.txt"
        write_private(identity_file, (identity.strip() + "\n").encode("ascii"))
        encrypt(decrypt(BACKUP, identity_file), recipient, output)


def request_restore(project_root, signing_directory):
    for tool in ("gh", "age", "age-keygen", "keytool"):
        if not shutil.which(tool):
            raise RuntimeError("缺少工具：{}".format(tool))
    with tempfile.TemporaryDirectory(prefix="h2-signing-recovery-") as directory:
        directory = Path(directory)
        identity = directory / "one-time-identity.txt"
        run(["age-keygen", "-o", str(identity)])
        identity.chmod(0o600)
        recipient = recipient_value(run(["age-keygen", "-y", str(identity)]).decode().strip())
        request_id = uuid.uuid4().hex
        title = "Android signing restore-backup " + request_id
        run(["gh", "workflow", "run", WORKFLOW, "--repo", REPOSITORY, "--ref", "main",
             "-f", "action=restore-backup", "-f", "recipient=" + recipient,
             "-f", "request_id=" + request_id])
        print("已提交恢复请求 {}，等待 GitHub 工作流。".format(request_id), flush=True)
        deadline = time.monotonic() + 1200
        previous = None
        while time.monotonic() < deadline:
            runs = json.loads(run([
                "gh", "run", "list", "--repo", REPOSITORY, "--workflow", WORKFLOW,
                "--branch", "main", "--event", "workflow_dispatch", "--limit", "30",
                "--json", "databaseId,displayTitle,status,conclusion,url",
            ]))
            matches = [item for item in runs if item["displayTitle"] == title]
            if len(matches) > 1:
                raise ValueError("恢复请求匹配到多个工作流，未下载")
            if matches:
                selected = matches[0]
                if selected["status"] != previous:
                    print("{} {}".format(selected["status"], selected["url"]), flush=True)
                    previous = selected["status"]
                if selected["status"] == "completed":
                    if selected["conclusion"] != "success":
                        raise RuntimeError("云端恢复失败，请查看上方工作流；本地文件未改变")
                    run_id = str(selected["databaseId"])
                    download = directory / "download"
                    run(["gh", "run", "download", run_id, "--repo", REPOSITORY,
                         "--name", "android-signing-" + run_id, "--dir", str(download)])
                    install_bundle(decrypt(download / "backup.json.age", identity), project_root, signing_directory)
                    return
            time.sleep(5)
        raise RuntimeError("等待恢复超时；可以重新执行请求，本地文件未改变")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("export-current", "rewrap-backup"):
        command = subparsers.add_parser(name)
        command.add_argument("--recipient", required=True, type=recipient_value)
        command.add_argument("--output", required=True, type=Path)
    for name in ("verify", "restore", "request"):
        command = subparsers.add_parser(name)
        if name != "request":
            command.add_argument("--backup", required=True, type=Path)
            command.add_argument("--identity", required=True, type=Path)
        if name != "verify":
            command.add_argument("--project-root", type=Path, default=ROOT)
            command.add_argument("--signing-dir", type=Path,
                                 default=Path.home() / ".config/hysteria2-manager/signing")
    args = parser.parse_args()
    try:
        if args.command == "export-current":
            encrypt(bundle_from_environment(), args.recipient, args.output)
        elif args.command == "rewrap-backup":
            rewrap_backup(args.recipient, args.output)
        elif args.command == "request":
            request_restore(args.project_root, args.signing_dir)
        else:
            bundle = decrypt(args.backup, args.identity)
            if args.command == "verify":
                print(json.dumps(check_key(bundle)))
            else:
                install_bundle(bundle, args.project_root, args.signing_dir)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, "操作失败：{}\n".format(exc))


if __name__ == "__main__":
    main()
