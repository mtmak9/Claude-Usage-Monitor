"""Generate small bundled WAV sounds for Claude Usage Monitor."""
from __future__ import annotations

import math
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SAMPLE_RATE = 44_100


def _env(t: float, start: float, duration: float) -> float:
    x = t - start
    if x < 0.0 or x > duration:
        return 0.0
    attack = 0.035
    release = 0.42
    if x < attack:
        return x / attack
    if x > duration - release:
        return max(0.0, (duration - x) / release)
    return 1.0


def _tone(t: float, freq: float) -> float:
    # A clean sine with tiny upper harmonics so the chime reads on laptop
    # speakers without becoming harsh.
    return (
        math.sin(2.0 * math.pi * freq * t)
        + 0.22 * math.sin(2.0 * math.pi * freq * 2.0 * t)
        + 0.10 * math.sin(2.0 * math.pi * freq * 3.0 * t)
    )


def _hit_env(t: float, start: float, duration: float) -> float:
    x = t - start
    if x < 0.0 or x > duration:
        return 0.0
    attack = 0.012
    release = 0.16
    if x < attack:
        return x / attack
    if x > duration - release:
        return max(0.0, (duration - x) / release)
    return 1.0


def generate_limit_hit(path: Path) -> None:
    duration = 0.92
    notes = (
        (0.00, 392.00, 0.30, 0.55),  # G4
        (0.19, 293.66, 0.42, 0.62),  # D4
        (0.49, 196.00, 0.22, 0.35),  # G3 tail
    )
    frames: list[float] = []
    for i in range(int(SAMPLE_RATE * duration)):
        t = i / SAMPLE_RATE
        sample = 0.0
        for start, freq, length, gain in notes:
            # Triangle-like harmonics: urgent, but not shrill.
            local = t - start
            sample += (
                math.sin(2.0 * math.pi * freq * local)
                + 0.35 * math.sin(2.0 * math.pi * freq * 2.0 * local)
                - 0.18 * math.sin(2.0 * math.pi * freq * 3.0 * local)
            ) * _hit_env(t, start, length) * gain
        if i >= int(0.045 * SAMPLE_RATE):
            sample += frames[i - int(0.045 * SAMPLE_RATE)] * 0.08
        frames.append(max(-0.95, min(0.95, sample * 0.38)))

    _write_wav(path, frames)


def generate_session_renewed(path: Path) -> None:
    duration = 1.28
    notes = (
        (0.00, 523.25, 0.62, 0.36),   # C5
        (0.12, 659.25, 0.70, 0.32),   # E5
        (0.26, 783.99, 0.78, 0.30),   # G5
        (0.42, 1046.50, 0.72, 0.22),  # C6 sparkle
    )
    frames: list[float] = []
    for i in range(int(SAMPLE_RATE * duration)):
        t = i / SAMPLE_RATE
        sample = 0.0
        for start, freq, length, gain in notes:
            sample += _tone(t - start, freq) * _env(t, start, length) * gain
        # A short ambience tail gives the sound a custom app identity while
        # keeping it under 1.3 seconds.
        if i >= int(0.07 * SAMPLE_RATE):
            sample += frames[i - int(0.07 * SAMPLE_RATE)] * 0.16
        if i >= int(0.13 * SAMPLE_RATE):
            sample += frames[i - int(0.13 * SAMPLE_RATE)] * 0.09
        frames.append(max(-0.95, min(0.95, sample * 0.34)))

    _write_wav(path, frames)


def _write_wav(path: Path, frames: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        payload = bytearray()
        for sample in frames:
            payload.extend(int(sample * 32767).to_bytes(2, "little", signed=True))
        wav.writeframes(bytes(payload))


def main() -> None:
    renewed = ROOT / "session_renewed.wav"
    limit_hit = ROOT / "limit_hit.wav"
    generate_session_renewed(renewed)
    generate_limit_hit(limit_hit)
    print(f"Wrote {renewed}")
    print(f"Wrote {limit_hit}")


if __name__ == "__main__":
    main()
