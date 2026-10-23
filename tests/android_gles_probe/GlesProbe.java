package test.hy2.glesprobe;

import android.app.Activity;
import android.opengl.EGL14;
import android.opengl.EGLConfig;
import android.opengl.EGLContext;
import android.opengl.EGLDisplay;
import android.opengl.EGLSurface;
import android.opengl.GLES30;
import android.os.Bundle;
import android.util.Log;
import java.io.BufferedReader;
import java.io.FileReader;

/** Standalone emulator diagnostic: no Flutter, network, storage or app data. */
public final class GlesProbe extends Activity {
    private static void check(boolean ok, String stage) {
        if (!ok) throw new IllegalStateException(stage);
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        new Thread(() -> {
            try {
                EGLDisplay display = EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY);
                int[] versions = new int[2];
                check(EGL14.eglInitialize(display, versions, 0, versions, 1), "initialize");
                EGLConfig[] configs = new EGLConfig[1];
                int[] count = new int[1];
                int[] attributes = {EGL14.EGL_RENDERABLE_TYPE, 0x40,
                    EGL14.EGL_SURFACE_TYPE, EGL14.EGL_PBUFFER_BIT, EGL14.EGL_NONE};
                check(EGL14.eglChooseConfig(display, attributes, 0, configs, 0, 1, count, 0)
                    && count[0] == 1, "choose ES3 config");
                EGLContext context = EGL14.eglCreateContext(display, configs[0],
                    EGL14.EGL_NO_CONTEXT, new int[]{EGL14.EGL_CONTEXT_CLIENT_VERSION, 3,
                        EGL14.EGL_NONE}, 0);
                EGLSurface surface = EGL14.eglCreatePbufferSurface(display, configs[0],
                    new int[]{EGL14.EGL_WIDTH, 16, EGL14.EGL_HEIGHT, 16, EGL14.EGL_NONE}, 0);
                check(EGL14.eglMakeCurrent(display, surface, surface, context), "make current");
                String renderer = GLES30.glGetString(GLES30.GL_RENDERER);
                boolean guestAngle = false;
                try (BufferedReader maps = new BufferedReader(new FileReader("/proc/self/maps"))) {
                    String line;
                    while ((line = maps.readLine()) != null) {
                        guestAngle |= line.endsWith("/libGLESv2_angle.so");
                    }
                }
                Log.i("Hy2GlesProbe", "renderer=" + renderer);
                Log.i("Hy2GlesProbe", "guestANGLELibraryLoaded=" + guestAngle);
                String expectedDriver = getIntent().getStringExtra("driver");
                check("default".equals(expectedDriver) || "guest-angle".equals(expectedDriver),
                    "missing expected driver");
                check(guestAngle == "guest-angle".equals(expectedDriver), "driver selection mismatch");
                if (guestAngle) {
                    check(renderer.contains("ANGLE") && renderer.contains("Vulkan"),
                        "expected guest ANGLE Vulkan renderer");
                }
                for (int attachments : new int[]{1, 0}) {
                    Log.i("Hy2GlesProbe", "begin numAttachments=" + attachments);
                    GLES30.glInvalidateFramebuffer(GLES30.GL_FRAMEBUFFER, attachments,
                        new int[]{GLES30.GL_COLOR}, 0);
                    GLES30.glFinish();
                    check(GLES30.glGetError() == GLES30.GL_NO_ERROR, "invalidate error");
                    Log.i("Hy2GlesProbe", "complete numAttachments=" + attachments);
                }
                EGL14.eglMakeCurrent(display, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_SURFACE,
                    EGL14.EGL_NO_CONTEXT);
                EGL14.eglDestroySurface(display, surface);
                EGL14.eglDestroyContext(display, context);
                EGL14.eglTerminate(display);
                Log.i("Hy2GlesProbe", "PROBE_PASSED");
            } catch (Throwable error) {
                Log.e("Hy2GlesProbe", "PROBE_FAILED", error);
            } finally {
                finish();
            }
        }, "gles-empty-attachments").start();
    }
}
