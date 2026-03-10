"""Azure Voice Live real-time voice session for DuckyAI."""

import asyncio
import base64
import json
import logging
import os
import queue
import signal
import sys
from typing import Union, Optional

import numpy as np
import sounddevice as sd

from azure.core.credentials import AzureKeyCredential
from azure.ai.voicelive.aio import connect
from azure.ai.voicelive.models import (
    AudioEchoCancellation,
    AudioNoiseReduction,
    AzureStandardVoice,
    FunctionCallOutputItem,
    InputAudioFormat,
    Modality,
    OutputAudioFormat,
    RequestSession,
    ServerEventType,
    ServerVad,
)

from .tools import get_vault_tools, handle_tool_call

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 1200  # 50ms at 24kHz


class VoiceLiveSession:
    """Real-time voice conversation using Azure Voice Live SDK with sounddevice."""

    def __init__(
        self,
        endpoint: str,
        credential,
        model: str = "gpt-4o-realtime-preview",
        voice: str = "en-US-Ava:DragonHDLatestNeural",
        instructions: str = "You are DuckyAI, a helpful personal knowledge assistant.",
        push_to_talk: bool = True,
    ):
        self.endpoint = endpoint
        self.credential = credential
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self.push_to_talk = push_to_talk
        self.connection = None
        self._loop = None

        # Audio state
        self._input_stream = None
        self._output_stream = None
        self._playback_queue = queue.Queue()
        self._playback_seq = 0
        self._playback_base = 0
        self._is_recording = False

        # Function call state
        self._pending_tool_calls = {}  # call_id -> {name, arguments}

    async def start(self):
        """Start the voice assistant session."""
        try:
            print("\n🔌 Connecting to Azure Voice Live...")
            async with connect(
                endpoint=self.endpoint,
                credential=self.credential,
                model=self.model,
            ) as conn:
                self.connection = conn
                self._loop = asyncio.get_event_loop()

                await self._setup_session()
                self._start_playback()

                if self.push_to_talk:
                    print("\n" + "=" * 50)
                    print("🎙️  DuckyAI Voice — Push-to-Talk")
                    print("   Hold [Space] to talk, release to send")
                    print("   Press [Q] to quit")
                    print("=" * 50 + "\n")
                    self._setup_push_to_talk()
                else:
                    print("\n" + "=" * 50)
                    print("🎙️  DuckyAI Voice — Open Mic")
                    print("   Speak naturally — VAD auto-detects your voice")
                    print("   Press Ctrl+C to exit")
                    print("=" * 50 + "\n")
                    self._start_capture()

                await self._process_events()
        finally:
            self._cleanup()

    async def _setup_session(self):
        """Configure session for voice conversation with tool support."""
        voice_config = AzureStandardVoice(name=self.voice) if "-" in self.voice else self.voice

        # Push-to-talk: disable server VAD, we control turn manually
        # Open mic: use server VAD for automatic turn detection
        if self.push_to_talk:
            turn_detection = None  # Manual turn control
        else:
            turn_detection = ServerVad(
                threshold=0.5,
                prefix_padding_ms=300,
                silence_duration_ms=500,
            )

        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            instructions=self.instructions,
            voice=voice_config,
            input_audio_format=InputAudioFormat.PCM16,
            output_audio_format=OutputAudioFormat.PCM16,
            turn_detection=turn_detection,
            input_audio_echo_cancellation=AudioEchoCancellation(),
            input_audio_noise_reduction=AudioNoiseReduction(type="azure_deep_noise_suppression"),
            tools=get_vault_tools(),
        )

        await self.connection.session.update(session=session_config)
        logger.info("Session configured (push_to_talk=%s)", self.push_to_talk)

    def _setup_push_to_talk(self):
        """Set up keyboard hooks for push-to-talk with Space key."""
        import keyboard

        def _on_space_press(event):
            if not self._is_recording:
                self._is_recording = True
                self._skip_playback()  # Stop any current playback
                self._start_capture()
                print("🔴 Recording... (release Space to send)", flush=True)

        def _on_space_release(event):
            if self._is_recording:
                self._is_recording = False
                self._stop_capture()
                print("⏹️  Sent! Waiting for response...", flush=True)
                # Commit the audio buffer and request a response
                if self._loop and self.connection:
                    asyncio.run_coroutine_threadsafe(
                        self._commit_and_respond(), self._loop
                    )

        def _on_q_press(event):
            print("\n👋 Quitting...", flush=True)
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)

        keyboard.on_press_key("space", _on_space_press, suppress=True)
        keyboard.on_release_key("space", _on_space_release, suppress=True)
        keyboard.on_press_key("q", _on_q_press)

    async def _commit_and_respond(self):
        """Commit audio buffer and request response (push-to-talk mode)."""
        try:
            await self.connection.input_audio_buffer.commit()
            await self.connection.response.create()
        except Exception as e:
            logger.error("Error committing audio: %s", e)

    def _start_capture(self):
        """Start streaming microphone audio to Voice Live."""
        def _mic_callback(indata, frames, time_info, status):
            if self.connection and self._loop:
                audio_b64 = base64.b64encode(indata.tobytes()).decode("utf-8")
                asyncio.run_coroutine_threadsafe(
                    self.connection.input_audio_buffer.append(audio=audio_b64),
                    self._loop,
                )

        self._input_stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=np.int16,
            blocksize=CHUNK_SIZE,
            callback=_mic_callback,
        )
        self._input_stream.start()
        logger.info("Microphone capture started")

    def _stop_capture(self):
        """Stop microphone capture (push-to-talk release)."""
        if self._input_stream:
            self._input_stream.stop()
            self._input_stream.close()
            self._input_stream = None
            logger.info("Microphone capture stopped")

    def _start_playback(self):
        """Start audio playback system."""
        remaining = bytearray()

        def _speaker_callback(outdata, frames, time_info, status):
            nonlocal remaining
            needed = frames * 2  # 2 bytes per sample (int16)

            out = bytes(remaining[:needed])
            remaining[:needed] = b""

            while len(out) < needed:
                try:
                    data = self._playback_queue.get_nowait()
                    if data is None:
                        break
                    out += data
                except queue.Empty:
                    break

            if len(out) < needed:
                out += b"\x00" * (needed - len(out))

            outdata[:] = np.frombuffer(out[:needed], dtype=np.int16).reshape(-1, 1)
            if len(out) > needed:
                remaining.extend(out[needed:])

        self._output_stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=np.int16,
            blocksize=CHUNK_SIZE,
            callback=_speaker_callback,
        )
        self._output_stream.start()
        logger.info("Speaker playback started")

    def _queue_audio(self, audio_data):
        """Queue audio data for playback. Handles both raw bytes and base64."""
        if isinstance(audio_data, str):
            # Base64-encoded audio from Voice Live
            raw = base64.b64decode(audio_data)
        elif isinstance(audio_data, bytes):
            raw = audio_data
        else:
            logger.warning("Unknown audio data type: %s", type(audio_data))
            return
        if raw:
            self._playback_queue.put(raw)

    def _skip_playback(self):
        """Clear pending playback (user interrupted)."""
        while not self._playback_queue.empty():
            try:
                self._playback_queue.get_nowait()
            except queue.Empty:
                break

    async def _process_events(self):
        """Main event loop processing Voice Live server events."""
        try:
            async for event in self.connection:
                await self._handle_event(event)
        except asyncio.CancelledError:
            pass

    async def _handle_event(self, event):
        """Handle individual Voice Live events."""
        etype = event.type
        logger.debug("Event: %s", etype)

        if etype == ServerEventType.SESSION_UPDATED:
            logger.info("Session ready: %s", event.session.id)
            if not self.push_to_talk:
                self._start_capture()

        elif etype == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            print("🎤 Listening...", flush=True)
            self._skip_playback()

        elif etype == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            print("🤔 Processing...", flush=True)

        elif etype == ServerEventType.RESPONSE_CREATED:
            logger.info("Response created")

        elif etype == ServerEventType.RESPONSE_AUDIO_DELTA:
            self._queue_audio(event.delta)

        elif etype == ServerEventType.RESPONSE_AUDIO_DONE:
            print("🔊 Response complete", flush=True)

        elif etype == ServerEventType.RESPONSE_DONE:
            if self.push_to_talk:
                print("🎤 Hold [Space] to talk...\n", flush=True)
            else:
                print("🎤 Ready...\n", flush=True)

        elif etype == ServerEventType.RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
            # Function call complete — execute the tool
            call_id = event.call_id
            name = event.name
            try:
                args = json.loads(event.arguments) if event.arguments else {}
            except json.JSONDecodeError:
                args = {}

            print(f"🔧 Tool: {name}({json.dumps(args, ensure_ascii=False)[:80]})", flush=True)
            result = await handle_tool_call(name, args)
            print(f"   → {result[:100]}{'...' if len(result) > 100 else ''}", flush=True)

            # Send result back to the model using proper SDK type
            output_item = FunctionCallOutputItem(call_id=call_id, output=result)
            await self.connection.conversation.item.create(item=output_item)
            # Trigger model to generate response based on tool result
            await self.connection.response.create()

        elif event.type == ServerEventType.ERROR:
            msg = event.error.message
            if "no active response" not in msg:
                print(f"⚠️  Error: {msg}", flush=True)
                logger.error("Voice Live error: %s", msg)

        elif event.type == ServerEventType.CONVERSATION_ITEM_CREATED:
            logger.debug("Conversation item created")

        else:
            # Log unhandled events for debugging
            logger.debug("Unhandled event: %s", event.type)

    def _cleanup(self):
        """Clean up audio resources."""
        if self._input_stream:
            self._input_stream.stop()
            self._input_stream.close()
        if self._output_stream:
            self._skip_playback()
            self._playback_queue.put(None)
            self._output_stream.stop()
            self._output_stream.close()
        # Unhook keyboard if push-to-talk was used
        if self.push_to_talk:
            try:
                import keyboard
                keyboard.unhook_all()
            except Exception:
                pass
        logger.info("Audio cleaned up")


async def run_voice_session(
    endpoint: str,
    credential,
    model: str = "gpt-4o-realtime-preview",
    voice: str = "en-US-Ava:DragonHDLatestNeural",
    instructions: str = "You are DuckyAI, a helpful personal knowledge assistant.",
    push_to_talk: bool = True,
):
    """Run a voice session."""
    session = VoiceLiveSession(
        endpoint=endpoint,
        credential=credential,
        model=model,
        voice=voice,
        instructions=instructions,
        push_to_talk=push_to_talk,
    )
    await session.start()
