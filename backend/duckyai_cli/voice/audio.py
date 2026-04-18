"""Audio capture and playback using sounddevice."""

import asyncio
import queue
import threading
import numpy as np

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = np.int16
BLOCK_SIZE = 2400  # 100ms at 24kHz


class AudioPlayer:
    """Plays PCM16 audio chunks through the default speaker."""

    def __init__(self):
        import sounddevice as sd
        self._sd = sd
        self._stream = None
        self._queue = queue.Queue()

    def start(self):
        self._stream = self._sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SIZE,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, outdata, frames, time_info, status):
        try:
            data = self._queue.get_nowait()
            if len(data) < len(outdata):
                outdata[:len(data)] = data
                outdata[len(data):] = 0
            else:
                outdata[:] = data[:len(outdata)]
        except queue.Empty:
            outdata[:] = 0

    def play(self, pcm_bytes: bytes):
        audio = np.frombuffer(pcm_bytes, dtype=DTYPE).reshape(-1, CHANNELS)
        # Split into chunks for smooth playback
        for i in range(0, len(audio), BLOCK_SIZE):
            chunk = audio[i:i + BLOCK_SIZE]
            if len(chunk) < BLOCK_SIZE:
                padded = np.zeros((BLOCK_SIZE, CHANNELS), dtype=DTYPE)
                padded[:len(chunk)] = chunk
                chunk = padded
            self._queue.put(chunk)

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()


class AudioRecorder:
    """Records PCM16 audio from the default microphone."""

    def __init__(self):
        import sounddevice as sd
        self._sd = sd
        self._recording = False
        self._chunks = []
        self._stream = None

    def start_recording(self):
        self._chunks = []
        self._recording = True
        self._stream = self._sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SIZE,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        if self._recording:
            self._chunks.append(indata.copy())

    def stop_recording(self) -> bytes:
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._chunks:
            audio = np.concatenate(self._chunks)
            return audio.tobytes()
        return b""
