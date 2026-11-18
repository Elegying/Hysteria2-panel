package vip.ssrvpn.hysteria2manager

import android.app.Activity
import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

class MainActivity : FlutterActivity() {
    private var pending: MethodChannel.Result? = null
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "hy2/files")
            .setMethodCallHandler { call, result ->
                if (call.method != "pickBackup") {
                    result.notImplemented()
                } else if (pending != null) {
                    result.error("BUSY", "文件选择正在进行", null)
                } else {
                    pending = result
                    try {
                        startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                            type = "application/zip"
                            addCategory(Intent.CATEGORY_OPENABLE)
                        }, 4102)
                    } catch (error: Exception) {
                        pending = null
                        result.error("PICK_FAILED", "无法打开文件选择器", null)
                    }
                }
            }
    }
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 4102) return
        val result = pending ?: return
        pending = null
        val uri = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) {
            result.success(null)
            return
        }
        Thread {
            var target: File? = null
            try {
                val outputFile = File.createTempFile("restore-", ".zip", cacheDir)
                target = outputFile
                contentResolver.openInputStream(uri).use { input ->
                    requireNotNull(input)
                    outputFile.outputStream().use { output ->
                        val buffer = ByteArray(64 * 1024)
                        var total = 0L
                        while (true) {
                            val count = input.read(buffer)
                            if (count < 0) break
                            total += count
                            require(total <= 131L * 1024 * 1024) { "Backup too large" }
                            output.write(buffer, 0, count)
                        }
                    }
                }
                val path = outputFile.absolutePath
                runOnUiThread { result.success(path) }
            } catch (error: Exception) {
                target?.delete()
                runOnUiThread { result.error("READ_FAILED", "无法读取备份文件", null) }
            }
        }.start()
    }
}
