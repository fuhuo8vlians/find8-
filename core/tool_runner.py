import os
import subprocess
import threading


class ToolRunner:
    def __init__(self):
        self._process = None
        self._running = False

    def run(self, work_dir, command, on_output, timeout=1800):
        self._running = True
        output_lines = []

        self._process = subprocess.Popen(
            command,
            shell=True,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
        )

        def read_stream(stream, stream_type):
            for line in iter(stream.readline, ""):
                if not self._running:
                    break
                line = line.rstrip()
                if line:
                    output_lines.append(line)
                    on_output({"type": stream_type, "line": line})
            stream.close()

        t_stdout = threading.Thread(
            target=read_stream, args=(self._process.stdout, "stdout"), daemon=True
        )
        t_stderr = threading.Thread(
            target=read_stream, args=(self._process.stderr, "stderr"), daemon=True
        )
        t_stdout.start()
        t_stderr.start()

        try:
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._process.kill()
            on_output({"type": "stderr", "line": f"[超时] 进程执行超过 {timeout} 秒，已终止"})
        finally:
            self._running = False
            t_stdout.join(timeout=2)
            t_stderr.join(timeout=2)

        return self._process.returncode, output_lines

    def stop(self):
        self._running = False
        if self._process and self._process.poll() is None:
            self._process.kill()
