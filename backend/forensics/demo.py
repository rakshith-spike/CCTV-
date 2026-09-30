"""Generate synthetic diagram footage locally; never represented as real CCTV."""
import subprocess


def generate(path):
    # Moving diagram of a person and a red backpack, 12 seconds at 8 FPS.
    command = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', '320x180', '-r', '8', '-i', '-', '-an', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in range(96):
            pixels = bytearray(bytes((24, 30, 34)) * (320 * 180))
            def rect(x, y, w, h, color):
                for row in range(y, min(y+h, 180)):
                    start = (row*320 + x)*3
                    pixels[start:start+w*3] = bytes(color)*w
            rect(0, 145, 320, 3, (90, 100, 110))
            rect(260, 35, 4, 110, (185, 219, 129))
            x = 20 + frame*2
            rect(x+8, 55, 16, 16, (200, 185, 150))
            rect(x+5, 72, 22, 42, (130, 145, 160))
            rect(x+4, 114, 8, 31, (100, 120, 140))
            rect(x+20, 114, 8, 31, (100, 120, 140))
            rect(x-5, 78, 12, 25, (220, 40, 40))
            proc.stdin.write(pixels)
        proc.stdin.close()
        error = proc.stderr.read()
        if proc.wait(timeout=30):
            raise RuntimeError(error.decode())
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
