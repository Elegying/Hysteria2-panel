"""Root-only isolated network-namespace check; never changes host firewall rules."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import node_agent  # noqa: E402


def main():
    if os.geteuid() != 0:
        raise SystemExit('requires root and network namespaces')
    suffix = uuid.uuid4().hex[:8]
    server, client = 'hy2s-' + suffix, 'hy2c-' + suffix
    interfaces = ('hs' + suffix, 'hc' + suffix)
    process = None

    def run(args, **kwargs):
        return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)

    def nft(args, **kwargs):
        return subprocess.run(['ip', 'netns', 'exec', server, *args], **kwargs)

    try:
        for namespace in (server, client):
            run(['ip', 'netns', 'add', namespace])
            run(['ip', '-n', namespace, 'link', 'set', 'lo', 'up'])
        run(['ip', 'link', 'add', interfaces[0], 'type', 'veth', 'peer', 'name', interfaces[1]])
        for index, namespace in enumerate((server, client)):
            device = interfaces[index]
            run(['ip', 'link', 'set', device, 'netns', namespace])
            run(['ip', '-n', namespace, 'addr', 'add', f'192.0.2.{index+1}/24', 'dev', device])
            run(['ip', '-n', namespace, '-6', 'addr', 'add', f'fd42::{index+1}/64', 'dev', device, 'nodad'])
            run(['ip', '-n', namespace, 'link', 'set', device, 'up'])
        nft(['/usr/sbin/nft', 'add', 'table', 'inet', 'unrelated'], check=True)
        listener = '''import socket,threading,time

def serve(family,kind):
 s=socket.socket(family,kind)
 if family==socket.AF_INET6:s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
 s.bind(('::' if family==socket.AF_INET6 else '0.0.0.0',443))
 if kind==socket.SOCK_STREAM:s.listen()
 while True:
  if kind==socket.SOCK_STREAM:
   c,_=s.accept();c.sendall(c.recv(64));c.close()
  else:
   data,peer=s.recvfrom(64);s.sendto(data,peer)
for family in (socket.AF_INET,socket.AF_INET6):
 for kind in (socket.SOCK_STREAM,socket.SOCK_DGRAM):
  threading.Thread(target=serve,args=(family,kind),daemon=True).start()
time.sleep(60)
'''
        process = subprocess.Popen(['ip', 'netns', 'exec', server, sys.executable, '-c', listener])
        time.sleep(0.3)
        probe = '''import socket,sys
for host,family in [('192.0.2.1',socket.AF_INET),('fd42::1',socket.AF_INET6)]:
 for kind in (socket.SOCK_STREAM,socket.SOCK_DGRAM):
  for port in [20000,35000,50000]:
   with socket.socket(family,kind) as s:
    s.settimeout(2);s.connect((host,port));s.send(b'probe');assert s.recv(64)==b'probe'
print('12 probes passed')
'''
        with tempfile.TemporaryDirectory() as folder:
            options = {'runner': nft, 'lock_path': str(Path(folder) / 'lock')}
            node_agent.configure_node_hopping(True, **options)
            first = run(['ip', 'netns', 'exec', client, sys.executable, '-c', probe]).stdout.strip()
            # A fresh kernel has no NAT table; applying persisted true recreates it.
            nft(['/usr/sbin/nft', 'delete', 'table', 'inet', 'hy2_port_hopping'], check=True)
            node_agent.configure_node_hopping(True, **options)
            run(['ip', 'netns', 'exec', client, sys.executable, '-c', probe])
            node_agent.configure_node_hopping(False, **options)
            node_agent.configure_node_hopping(False, check_only=True, **options)
            run(['ip', 'netns', 'exec', client, sys.executable, '-c',
                 probe.replace('[20000,35000,50000]', '[443]')])
            disabled_probe = 'import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(0.3); s.sendto(b"probe",("192.0.2.1",25001)); s.recv(64)'
            disabled = subprocess.run(['ip', 'netns', 'exec', client, sys.executable, '-c', disabled_probe], capture_output=True)
            if disabled.returncode == 0:
                raise AssertionError('disabled hopping still accepted a fresh UDP flow')
            nft(['/usr/sbin/nft', 'list', 'table', 'inet', 'unrelated'], check=True)
            print(json.dumps({'ipv4_ipv6_udp_tcp': first, 'restart_recovery': True,
                              'disabled_cleanup': True, 'unrelated_table_preserved': True}))
    finally:
        if process:
            process.terminate()
            process.wait(timeout=5)
        for namespace in (server, client):
            subprocess.run(['ip', 'netns', 'del', namespace], capture_output=True)


if __name__ == '__main__':
    main()
