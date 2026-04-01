import os
import soundfile as sf

from config import ROOT_DIR, get_tts_voice

KITTEN_MODEL = "KittenML/kitten-tts-mini-0.8"
KITTEN_SAMPLE_RATE = 24000

class TTS:
    def __init__(self) -> None:
        try:
            from kittentts import KittenTTS as KittenModel
            self._model = KittenModel(KITTEN_MODEL)
        except ImportError:
            self._model = None
            print("[TTS] kittentts is not installed — TTS will not work. Required for YouTube Shorts.")
        self._voice = get_tts_voice()

    def synthesize(self, text, output_file=os.path.join(ROOT_DIR, ".mp", "audio.wav")):
        if self._model is None:
            raise RuntimeError("kittentts is not installed. Cannot synthesize audio.")
        audio = self._model.generate(text, voice=self._voice)
        sf.write(output_file, audio, KITTEN_SAMPLE_RATE)
        return output_file
