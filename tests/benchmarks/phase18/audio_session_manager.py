"""
Phase 18A: AudioSessionManager Architecture Specification & Core Implementation
Stateful session supervisor managing microphone capture, ring buffer, VAD,
STT streaming, TTS playback, and sub-40ms barge-in cancellation.
Voice is strictly an I/O surface for TaskRuntime, NOT an independent agent.
"""

import time
import threading
from enum import Enum
from typing import Optional, Callable, List, Tuple
from collections import deque
from dataclasses import dataclass, field

class AudioSessionState(str, Enum):
    IDLE = "IDLE"                  # Stream closed or silent; VAD in low-power idle
    LISTENING = "LISTENING"        # Microphone active; capturing chunks into ring buffer
    TRANSCRIBING = "TRANSCRIBING"  # VAD endpoint detected; routing audio to STT engine
    THINKING = "THINKING"          # STT complete; TaskRuntime / CognitiveRouter active
    SPEAKING = "SPEAKING"          # TTS output streaming to speaker
    INTERRUPTED = "INTERRUPTED"    # User barge-in triggered; flushing audio output buffer
    MIC_DISABLED = "MIC_DISABLED"  # Hard privacy killswitch engaged; OS mic handle closed

@dataclass
class AudioConfig:
    sample_rate: int = 16000
    chunk_samples: int = 512       # 32 ms chunk at 16 kHz
    channels: int = 1
    pre_roll_chunks: int = 4       # ~128 ms pre-speech ring buffer
    max_silence_chunks: int = 15   # ~480 ms silence for endpointing
    barge_in_threshold: float = 0.5

class AudioSessionManager:
    """Manages audio device lifecycle, VAD states, TTS cancellation, and barge-in."""

    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig()
        self.state = AudioSessionState.IDLE
        self._state_lock = threading.RLock()
        
        # 500ms sliding circular buffer for audio pre-roll
        self._ring_buffer = deque(maxlen=self.config.pre_roll_chunks)
        self._active_utterance_chunks: List[bytes] = []
        
        # Subsystem callbacks
        self.on_state_change: Optional[Callable[[AudioSessionState], None]] = None
        self.on_transcript_ready: Optional[Callable[[str], None]] = None
        self.on_barge_in: Optional[Callable[[float], None]] = None
        
        # Physical device simulation flags
        self._is_mic_open = False
        self._is_speaker_active = False
        self._last_speech_onset_ns = 0
        self._silence_chunk_count = 0

    def transition_to(self, new_state: AudioSessionState):
        with self._state_lock:
            if self.state == new_state:
                return
            if self.state == AudioSessionState.MIC_DISABLED and new_state != AudioSessionState.IDLE:
                # Disallow exiting MIC_DISABLED without explicit enable
                return
            old_state = self.state
            self.state = new_state
            if self.on_state_change:
                self.on_state_change(new_state)

    def engage_microphone_killswitch(self):
        """Hard software/hardware privacy killswitch. Closes mic immediately."""
        with self._state_lock:
            self._is_mic_open = False
            self._ring_buffer.clear()
            self._active_utterance_chunks.clear()
            self.transition_to(AudioSessionState.MIC_DISABLED)

    def disengage_microphone_killswitch(self):
        """Disengages killswitch and restores IDLE state."""
        with self._state_lock:
            if self.state == AudioSessionState.MIC_DISABLED:
                self.state = AudioSessionState.IDLE
                if self.on_state_change:
                    self.on_state_change(AudioSessionState.IDLE)

    def start_listening(self):
        """Begins audio capture into pre-roll buffer (PTT or hotkey trigger)."""
        with self._state_lock:
            if self.state == AudioSessionState.MIC_DISABLED:
                return False
            self._is_mic_open = True
            self._silence_chunk_count = 0
            self._ring_buffer.clear()
            self._active_utterance_chunks.clear()
            self.transition_to(AudioSessionState.LISTENING)
            return True

    def process_incoming_audio_chunk(self, chunk_bytes: bytes, vad_speech_prob: float) -> Tuple[AudioSessionState, Optional[bytes]]:
        """
        Called on every 32ms audio chunk from microphone stream.
        Handles VAD speech onset, endpointing, and barge-in.
        """
        with self._state_lock:
            if self.state == AudioSessionState.MIC_DISABLED:
                return self.state, None

            is_speech = vad_speech_prob >= self.config.barge_in_threshold

            # 1. Handle Barge-In during SPEAKING state
            if self.state == AudioSessionState.SPEAKING:
                if is_speech:
                    # User interrupted Astra while Astra was speaking!
                    t_interrupt = time.perf_counter()
                    self.abort_speech_playback()
                    self.transition_to(AudioSessionState.INTERRUPTED)
                    if self.on_barge_in:
                        self.on_barge_in(t_interrupt)
                    # Prepend pre-roll and start capturing new utterance
                    self._active_utterance_chunks = list(self._ring_buffer)
                    self._active_utterance_chunks.append(chunk_bytes)
                    self.transition_to(AudioSessionState.LISTENING)
                    return self.state, None
                else:
                    # Still speaking, user is silent; push chunk to ring buffer
                    self._ring_buffer.append(chunk_bytes)
                    return self.state, None

            # 2. Handle LISTENING state
            if self.state == AudioSessionState.LISTENING:
                if is_speech:
                    if not self._active_utterance_chunks:
                        # Speech onset! Prepend pre-roll buffer
                        self._active_utterance_chunks = list(self._ring_buffer)
                    self._active_utterance_chunks.append(chunk_bytes)
                    self._silence_chunk_count = 0
                else:
                    if self._active_utterance_chunks:
                        # User was speaking, now silent
                        self._active_utterance_chunks.append(chunk_bytes)
                        self._silence_chunk_count += 1
                        if self._silence_chunk_count >= self.config.max_silence_chunks:
                            # Endpoint reached! Complete utterance
                            completed_audio = b"".join(self._active_utterance_chunks)
                            self._active_utterance_chunks.clear()
                            self.transition_to(AudioSessionState.TRANSCRIBING)
                            return self.state, completed_audio
                    else:
                        # Ongoing silence before speech; keep ring buffer fresh
                        self._ring_buffer.append(chunk_bytes)

            return self.state, None

    def begin_speaking(self):
        """Called when TaskRuntime sends TTS audio stream to speakers."""
        with self._state_lock:
            self._is_speaker_active = True
            self.transition_to(AudioSessionState.SPEAKING)

    def finish_speaking(self):
        """Called when TTS audio stream ends naturally."""
        with self._state_lock:
            self._is_speaker_active = False
            if self.state == AudioSessionState.SPEAKING:
                self.transition_to(AudioSessionState.IDLE)

    def abort_speech_playback(self) -> float:
        """
        Immediately flushes audio hardware buffer (WASAPI buffer reset / abort).
        Returns the hardware abort latency in ms.
        """
        t0 = time.perf_counter()
        self._is_speaker_active = False
        # Hardware flush simulation (< 5 ms)
        abort_latency_ms = (time.perf_counter() - t0) * 1000.0
        return abort_latency_ms
