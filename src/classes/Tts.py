import os
import asyncio

from config import ROOT_DIR, get_tts_voice

# Maps friendly config names to edge-tts voice identifiers.
# Full edge-tts voice names (e.g. "en-US-GuyNeural") are also accepted directly.
VOICE_MAP = {
    "Jasper":      "en-US-ChristopherNeural",
    "Guy":         "en-US-GuyNeural",
    "Jenny":       "en-US-JennyNeural",
    "Aria":        "en-US-AriaNeural",
    "Ryan":        "en-GB-RyanNeural",
    "Sonia":       "en-GB-SoniaNeural",
    "Eric":        "en-US-EricNeural",
    "Michelle":    "en-US-MichelleNeural",
}

DEFAULT_VOICE = "en-US-ChristopherNeural"


class TTS:
    def __init__(self) -> None:
        configured = get_tts_voice()
        self._voice = VOICE_MAP.get(configured, configured) or DEFAULT_VOICE

    def synthesize(self, text: str, output_file: str = os.path.join(ROOT_DIR, ".mp", "audio.mp3")) -> str:
        """
        Converts text to speech using Microsoft Edge TTS (free, no API key).

        Args:
            text (str): The text to synthesize.
            output_file (str): Destination path for the audio file (MP3).

        Returns:
            str: Path to the generated audio file.
        """
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(text, self._voice)
            await communicate.save(output_file)

        asyncio.run(_run())
        return output_file
