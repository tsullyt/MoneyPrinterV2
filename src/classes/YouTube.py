import re
import base64
import json
import time
import os
import requests
import assemblyai as aai

from utils import *
from cache import *
from .Tts import TTS
from llm_provider import generate_text
from config import *
from status import *
from uuid import uuid4
from constants import *
from typing import List
from moviepy.editor import *
from termcolor import colored
from selenium import webdriver
from moviepy.video.fx.all import crop
from moviepy.config import change_settings
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.keys import Keys
from moviepy.video.tools.subtitles import SubtitlesClip
from webdriver_manager.firefox import GeckoDriverManager
from datetime import datetime

# Set ImageMagick Path
change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})

# Pillow 10+ removed ANTIALIAS — patch it back so MoviePy 1.x doesn't crash
import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS


class YouTube:
    """
    Class for YouTube Automation.

    Steps to create a YouTube Short:
    1. Generate a topic [DONE]
    2. Generate a script [DONE]
    3. Generate metadata (Title, Description, Tags) [DONE]
    4. Generate AI Image Prompts [DONE]
    4. Generate Images based on generated Prompts [DONE]
    5. Convert Text-to-Speech [DONE]
    6. Show images each for n seconds, n: Duration of TTS / Amount of images [DONE]
    7. Combine Concatenated Images with the Text-to-Speech [DONE]
    """

    def __init__(
        self,
        account_uuid: str,
        account_nickname: str,
        fp_profile_path: str,
        niche: str,
        language: str,
    ) -> None:
        """
        Constructor for YouTube Class.

        Args:
            account_uuid (str): The unique identifier for the YouTube account.
            account_nickname (str): The nickname for the YouTube account.
            fp_profile_path (str): Path to the firefox profile that is logged into the specificed YouTube Account.
            niche (str): The niche of the provided YouTube Channel.
            language (str): The language of the Automation.

        Returns:
            None
        """
        self._account_uuid: str = account_uuid
        self._account_nickname: str = account_nickname
        self._fp_profile_path: str = fp_profile_path
        self._niche: str = niche
        self._language: str = language

        self.images = []

        # Initialize the Firefox profile
        self.options: Options = Options()

        # Set headless state of browser
        if get_headless():
            self.options.add_argument("--headless")

        if not os.path.isdir(self._fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {self._fp_profile_path}"
            )

        self.options.add_argument("-profile")
        self.options.add_argument(self._fp_profile_path)

        self.browser: webdriver.Firefox = None

    @property
    def niche(self) -> str:
        """
        Getter Method for the niche.

        Returns:
            niche (str): The niche
        """
        return self._niche

    @property
    def language(self) -> str:
        """
        Getter Method for the language to use.

        Returns:
            language (str): The language
        """
        return self._language

    def generate_response(self, prompt: str, model_name: str = None) -> str:
        """
        Generates an LLM Response based on a prompt and the user-provided model.

        Args:
            prompt (str): The prompt to use in the text generation.

        Returns:
            response (str): The generated AI Repsonse.
        """
        return generate_text(prompt, model_name=model_name)

    def generate_topic(self) -> str:
        """
        Generates a topic based on the YouTube Channel niche.

        Returns:
            topic (str): The generated topic.
        """
        completion = self.generate_response(
            f"Please generate a specific video idea that takes about the following topic: {self.niche}. Make it exactly one sentence. Only return the topic, nothing else."
        )

        if not completion:
            error("Failed to generate Topic.")

        self.subject = completion

        return completion

    def generate_script(self) -> str:
        """
        Generate a script for a video, depending on the subject of the video, the number of paragraphs, and the AI model.

        Returns:
            script (str): The script of the video.
        """
        sentence_length = get_script_sentence_length()
        prompt = f"""
Role: You are a YouTube Shorts scriptwriter specializing in short, punchy narration.

Instructions: Write a voiceover script for a YouTube Short about the subject below.

Steps:
1. Write exactly {sentence_length} sentences — no more, no fewer.
2. Each sentence must be 10 words or fewer.
3. Every sentence must end with a period, exclamation mark, or question mark.
4. Do not join clauses with "and", "but", "so", or "because".
5. Get straight to the point — do not open with "welcome" or any introduction.
6. Do not use markdown, bullet points, titles, or any formatting.
7. Do not label lines with "Narrator:", "Voiceover:", or anything similar.
8. Do not reference this prompt or mention the script itself.

End goal: A script that sounds natural when read aloud — punchy, with clear pauses between ideas and no run-on sentences.

Narrowing:
- Subject: {self.subject}
- Language: {self.language}
- Return only the raw script. Absolutely nothing else.
        """
        completion = self.generate_response(prompt)

        # Apply regex to remove *
        completion = re.sub(r"\*", "", completion)

        # Ensure each sentence ends with punctuation so TTS pauses correctly
        sentences = re.split(r'(?<=[.!?])\s+', completion.strip())
        fixed = []
        for s in sentences:
            s = s.strip()
            if s and s[-1] not in ".!?":
                s += "."
            if s:
                fixed.append(s)
        completion = " ".join(fixed)

        if not completion:
            error("The generated script is empty.")
            return

        if len(completion) > 5000:
            if get_verbose():
                warning("Generated Script is too long. Retrying...")
            return self.generate_script()

        self.script = completion

        return completion

    def generate_metadata(self) -> dict:
        """
        Generates Video metadata for the to-be-uploaded YouTube Short (Title, Description).

        Returns:
            metadata (dict): The generated metadata.
        """
        title = self.generate_response(
            f"Please generate a YouTube Video Title for the following subject, including hashtags: {self.subject}. Only return the title, nothing else. Limit the title under 100 characters."
        )

        if len(title) > 100:
            if get_verbose():
                warning("Generated Title is too long. Retrying...")
            return self.generate_metadata()

        description = self.generate_response(
            f"Please generate a YouTube Video Description for the following script: {self.script}. "
            f"Do not include any URLs, hyperlinks, or 'Full story' lines — those will be added separately. "
            f"Only return the description, nothing else."
        )
        # Strip any URL lines the LLM may have hallucinated (e.g. "Full story: https://...")
        description_lines = [
            line for line in description.splitlines()
            if "http" not in line and "Full story" not in line
        ]
        description = "\n".join(description_lines).strip()

        self.metadata = {"title": title, "description": description}

        return self.metadata

    def generate_prompts(self) -> List[str]:
        """
        Generates AI Image Prompts based on the provided Video Script.

        Returns:
            image_prompts (List[str]): Generated List of image prompts.
        """
        n_prompts = 4

        prompt = f"""
        Generate {n_prompts} Image Prompts for AI Image Generation,
        depending on the subject of a video.
        Subject: {self.subject}

        The image prompts are to be returned as
        a JSON-Array of strings.

        Each search term should consist of a full sentence,
        always add the main subject of the video.

        Be emotional and use interesting adjectives to make the
        Image Prompt as detailed as possible.

        YOU MUST ONLY RETURN THE JSON-ARRAY OF STRINGS.
        YOU MUST NOT RETURN ANYTHING ELSE.
        YOU MUST NOT RETURN THE SCRIPT.

        The search terms must be related to the subject of the video.
        Here is an example of a JSON-Array of strings:
        ["image prompt 1", "image prompt 2", "image prompt 3"]

        For context, here is the full text:
        {self.script}
        """

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
        )

        image_prompts = []

        if "image_prompts" in completion:
            image_prompts = json.loads(completion)["image_prompts"]
        else:
            try:
                image_prompts = json.loads(completion)
                if get_verbose():
                    info(f" => Generated Image Prompts: {image_prompts}")
            except Exception:
                if get_verbose():
                    warning(
                        "LLM returned an unformatted response. Attempting to clean..."
                    )

                # Get everything between [ and ], and turn it into a list
                r = re.compile(r"\[.*\]")
                image_prompts = r.findall(completion)
                if len(image_prompts) == 0:
                    if get_verbose():
                        warning("Failed to generate Image Prompts. Retrying...")
                    return self.generate_prompts()

        if len(image_prompts) > n_prompts:
            image_prompts = image_prompts[:n_prompts]

        self.image_prompts = image_prompts

        success(f"Generated {len(image_prompts)} Image Prompts.")

        return image_prompts

    def _persist_image(self, image_bytes: bytes, provider_label: str) -> str:
        """
        Writes generated image bytes to a PNG file in .mp.

        Args:
            image_bytes (bytes): Image payload
            provider_label (str): Label for logging

        Returns:
            path (str): Absolute image path
        """
        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")

        with open(image_path, "wb") as image_file:
            image_file.write(image_bytes)

        if get_verbose():
            info(f' => Wrote image from {provider_label} to "{image_path}"')

        self.images.append(image_path)
        return image_path

    def generate_image_nanobanana2(self, prompt: str) -> str:
        """
        Generates an AI Image using Nano Banana 2 API (Gemini image API).

        Args:
            prompt (str): Prompt for image generation

        Returns:
            path (str): The path to the generated image.
        """
        print(f"Generating Image using Nano Banana 2 API: {prompt}")

        api_key = get_nanobanana2_api_key()
        if not api_key:
            error("nanobanana2_api_key is not configured.")
            return None

        base_url = get_nanobanana2_api_base_url().rstrip("/")
        model = get_nanobanana2_model()
        aspect_ratio = get_nanobanana2_aspect_ratio()

        endpoint = f"{base_url}/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        }

        for attempt in range(3):
            try:
                response = requests.post(
                    endpoint,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=300,
                )
                if response.status_code == 429:
                    wait = 15 * (attempt + 1)
                    warning(f"Gemini rate limit hit. Waiting {wait}s before retry {attempt + 1}/3...")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                body = response.json()

                candidates = body.get("candidates", [])
                for candidate in candidates:
                    content = candidate.get("content", {})
                    for part in content.get("parts", []):
                        inline_data = part.get("inlineData") or part.get("inline_data")
                        if not inline_data:
                            continue
                        data = inline_data.get("data")
                        mime_type = inline_data.get("mimeType") or inline_data.get("mime_type", "")
                        if data and str(mime_type).startswith("image/"):
                            image_bytes = base64.b64decode(data)
                            return self._persist_image(image_bytes, "Nano Banana 2 API")

                if get_verbose():
                    warning(f"Nano Banana 2 did not return an image payload. Response: {body}")
                return None
            except Exception as e:
                if get_verbose():
                    warning(f"Failed to generate image with Nano Banana 2 API: {str(e)}")
                return None
        warning("Failed to generate image after 3 attempts (rate limit).")
        return None

    def generate_image_pollinations(self, prompt: str) -> str:
        """
        Generates an image using Pollinations.ai (free, no API key required).
        """
        from urllib.parse import quote

        aspect = get_nanobanana2_aspect_ratio()
        try:
            w_ratio, h_ratio = [int(x) for x in aspect.split(":")]
        except Exception:
            w_ratio, h_ratio = 9, 16

        base_unit = 64
        width = w_ratio * base_unit   # 576 for 9:16
        height = h_ratio * base_unit  # 1024 for 9:16

        url = (
            f"https://image.pollinations.ai/prompt/{quote(prompt, safe='')}"
            f"?width={width}&height={height}&nologo=true"
        )

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"}
        for attempt in range(5):
            try:
                response = requests.get(url, headers=headers, timeout=120)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if content_type.startswith("image/"):
                    return self._persist_image(response.content, "Pollinations.ai")
                if get_verbose():
                    warning(f"Pollinations did not return an image. Content-Type: {content_type}")
            except Exception as e:
                if get_verbose():
                    warning(f"Pollinations attempt {attempt + 1}/5 failed: {str(e)}")
            if attempt < 4:
                time.sleep(15)
        return None

    def generate_image_pexels(self, prompt: str) -> str:
        """
        Fetches a relevant stock photo from Pexels (free, requires API key).
        Searches using the prompt text and downloads the best portrait-orientation result.
        """
        api_key = get_pexels_api_key()
        if not api_key:
            if get_verbose():
                warning("pexels_api_key not set in config. Falling back to Pollinations.")
            return self.generate_image_pollinations(prompt)

        # Trim prompt to a short search query (Pexels works best with 3-6 words)
        words = prompt.split()
        query = " ".join(words[:6])

        headers = {"Authorization": api_key}
        params = {"query": query, "orientation": "portrait", "per_page": 5}

        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                headers=headers,
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            photos = r.json().get("photos", [])

            if not photos:
                if get_verbose():
                    warning(f"Pexels returned no results for '{query}'. Falling back to Pollinations.")
                return self.generate_image_pollinations(prompt)

            # Pick the first result and download its large2x (portrait) version
            photo_url = photos[0]["src"]["large2x"]
            img_response = requests.get(photo_url, timeout=30)
            img_response.raise_for_status()
            return self._persist_image(img_response.content, "Pexels")

        except Exception as e:
            if get_verbose():
                warning(f"Pexels image fetch failed: {str(e)}. Falling back to Pollinations.")
            return self.generate_image_pollinations(prompt)

    def generate_image(self, prompt: str) -> str:
        """
        Generates an AI Image based on the given prompt.

        Args:
            prompt (str): Reference for image generation

        Returns:
            path (str): The path to the generated image.
        """
        return self.generate_image_pexels(prompt)

    def generate_script_to_speech(self, tts_instance: TTS) -> str:
        """
        Converts the generated script into Speech using KittenTTS and returns the path to the wav file.

        Args:
            tts_instance (tts): Instance of TTS Class.

        Returns:
            path_to_wav (str): Path to generated audio (WAV Format).
        """
        path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp3")

        # Clean script, remove every character that is not a word character, a space, a period, a question mark, or an exclamation mark.
        self.script = re.sub(r"[^\w\s.?!]", "", self.script)

        tts_instance.synthesize(self.script, path)

        self.tts_path = path

        if get_verbose():
            info(f' => Wrote TTS to "{path}"')

        return path

    def add_video(self, video: dict) -> None:
        """
        Adds a video to the cache.

        Args:
            video (dict): The video to add

        Returns:
            None
        """
        videos = self.get_videos()
        videos.append(video)

        cache = get_youtube_cache_path()

        with open(cache, "r") as file:
            previous_json = json.loads(file.read())

            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    account["videos"].append(video)

            # Commit changes
            with open(cache, "w") as f:
                f.write(json.dumps(previous_json))

    def generate_subtitles(self, audio_path: str) -> str:
        """
        Generates subtitles for the audio using the configured STT provider.

        Args:
            audio_path (str): The path to the audio file.

        Returns:
            path (str): The path to the generated SRT File.
        """
        provider = str(get_stt_provider() or "local_whisper").lower()

        if provider == "local_whisper":
            return self.generate_subtitles_local_whisper(audio_path)

        if provider == "third_party_assemblyai":
            return self.generate_subtitles_assemblyai(audio_path)

        warning(f"Unknown stt_provider '{provider}'. Falling back to local_whisper.")
        return self.generate_subtitles_local_whisper(audio_path)

    def generate_subtitles_assemblyai(self, audio_path: str) -> str:
        """
        Generates subtitles using AssemblyAI.

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        aai.settings.api_key = get_assemblyai_api_key()
        config = aai.TranscriptionConfig()
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_path)
        subtitles = transcript.export_subtitles_srt()

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")

        with open(srt_path, "w") as file:
            file.write(subtitles)

        return srt_path

    def _format_srt_timestamp(self, seconds: float) -> str:
        """
        Formats a timestamp in seconds to SRT format.

        Args:
            seconds (float): Seconds

        Returns:
            ts (str): HH:MM:SS,mmm
        """
        total_millis = max(0, int(round(seconds * 1000)))
        hours = total_millis // 3600000
        minutes = (total_millis % 3600000) // 60000
        secs = (total_millis % 60000) // 1000
        millis = total_millis % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def generate_subtitles_local_whisper(self, audio_path: str) -> str:
        """
        Generates subtitles using local Whisper (faster-whisper).

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            error(
                "Local STT selected but 'faster-whisper' is not installed. "
                "Install it or switch stt_provider to third_party_assemblyai."
            )
            raise

        model = WhisperModel(
            get_whisper_model(),
            device=get_whisper_device(),
            compute_type=get_whisper_compute_type(),
        )
        segments, _ = model.transcribe(audio_path, vad_filter=True)

        lines = []
        for idx, segment in enumerate(segments, start=1):
            start = self._format_srt_timestamp(segment.start)
            end = self._format_srt_timestamp(segment.end)
            text = str(segment.text).strip()

            if not text:
                continue

            lines.append(str(idx))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        subtitles = "\n".join(lines)
        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write(subtitles)

        return srt_path

    def combine(self) -> str:
        """
        Combines everything into the final video.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        if not self.images:
            raise RuntimeError("No images were generated — cannot combine video. Check Gemini API key and rate limits.")
        combined_image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration
        req_dur = max_duration / len(self.images)

        # Make a generator that returns a TextClip when called with consecutive
        generator = lambda txt: TextClip(
            txt,
            font=os.path.join(get_fonts_dir(), get_font()),
            fontsize=100,
            color="#FFFF00",
            stroke_color="black",
            stroke_width=5,
            size=(1080, 300),
            method="caption",
        )

        print(colored("[+] Combining images...", "blue"))

        clips = []
        tot_dur = 0
        # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
        while tot_dur < max_duration:
            for image_path in self.images:
                clip = ImageClip(image_path)
                clip.duration = req_dur
                clip = clip.set_fps(30)

                # Not all images are same size,
                # so we need to resize them
                if round((clip.w / clip.h), 4) < 0.5625:
                    if get_verbose():
                        info(f" => Resizing Image: {image_path} to 1080x1920")
                    clip = crop(
                        clip,
                        width=clip.w,
                        height=round(clip.w / 0.5625),
                        x_center=clip.w / 2,
                        y_center=clip.h / 2,
                    )
                else:
                    if get_verbose():
                        info(f" => Resizing Image: {image_path} to 1920x1080")
                    clip = crop(
                        clip,
                        width=round(0.5625 * clip.h),
                        height=clip.h,
                        x_center=clip.w / 2,
                        y_center=clip.h / 2,
                    )
                clip = clip.resize((1080, 1920))

                # FX (Fade In)
                # clip = clip.fadein(2)

                clips.append(clip)
                tot_dur += clip.duration

        final_clip = concatenate_videoclips(clips)
        final_clip = final_clip.set_fps(30)
        random_song = choose_random_song()

        subtitles = None
        try:
            subtitles_path = self.generate_subtitles(self.tts_path)
            equalize_subtitles(subtitles_path, 30)
            subtitles = SubtitlesClip(subtitles_path, generator)
            subtitles.set_pos(("center", 1550))
        except Exception as e:
            warning(f"Failed to generate subtitles, continuing without subtitles: {e}")

        random_song_clip = AudioFileClip(random_song).set_fps(44100)

        # Turn down volume
        random_song_clip = random_song_clip.fx(afx.volumex, 0.1)
        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), random_song_clip])

        final_clip = final_clip.set_audio(comp_audio)
        final_clip = final_clip.set_duration(tts_clip.duration)

        if subtitles is not None:
            final_clip = CompositeVideoClip([final_clip, subtitles])

        final_clip.write_videofile(combined_image_path, threads=threads)

        success(f'Wrote Video to "{combined_image_path}"')

        return combined_image_path

    def generate_video(self, tts_instance: TTS) -> str:
        """
        Generates a YouTube Short based on the provided niche and language.

        Args:
            tts_instance (TTS): Instance of TTS Class.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        # Generate the Topic
        self.generate_topic()

        # Generate the Script
        self.generate_script()

        # Generate the Metadata
        self.generate_metadata()

        # Generate the Image Prompts
        self.generate_prompts()

        # Generate the Images
        for i, prompt in enumerate(self.image_prompts):
            if i > 0:
                time.sleep(10)
            self.generate_image(prompt)

        if not self.images:
            raise RuntimeError("Image generation failed for all prompts. Check Gemini API key and rate limits.")

        # Generate the TTS
        self.generate_script_to_speech(tts_instance)

        # Combine everything
        path = self.combine()

        if get_verbose():
            info(f" => Generated Video: {path}")

        self.video_path = os.path.abspath(path)

        return path

    def fetch_news_article(self) -> dict:
        """
        Fetches the top financial news article via RSS feeds and stores it
        in self.article for use by generate_news_script().

        Returns:
            dict: Article with keys title, summary, url, source_name, published.
        """
        from scrapers.news_scraper import fetch_top_article
        seen_urls = set()
        for video in self.get_videos():
            desc = video.get("description", "")
            if "Full story: " in desc:
                seen_urls.add(desc.split("Full story: ")[-1].strip())
        article = fetch_top_article(seen_urls=seen_urls)
        self.article = article
        if get_verbose():
            safe_title = article['title'].encode('ascii', 'replace').decode()
            info(f" => Fetched article: {safe_title} ({article['source_name']})")
        return article

    def generate_news_script(self) -> str:
        """
        Uses Ollama to summarize self.article into a short spoken script.
        Does not embellish — cites the source at the end.

        Returns:
            str: The generated script stored in self.script.
        """
        article = self.article
        content = article["summary"] if article.get("summary") else article["title"]
        prompt = (
            f"Summarize the following financial news in 5 to 8 concise sentences "
            f"suitable for a short spoken video. Do not add opinions, speculation, "
            f"or information not present in the source. Write in plain spoken English. "
            f"Do not include any preamble, intro phrase, or meta-commentary — start "
            f"directly with the news content. "
            f"End with exactly this sentence: 'Source, {article['source_name']}.'\n\n"
            f"Article title: {article['title']}\n"
            f"Article content: {content}"
        )
        script = self.generate_response(prompt).replace("*", "").strip()
        if len(script) > 5000:
            script = script[:5000]
        self.script = script
        self.subject = article["title"]
        if get_verbose():
            info(f" => Generated news script ({len(script)} chars)")
        return script

    def generate_news_video(self, tts_instance: TTS) -> str:
        """
        Generates a YouTube Short from a live financial news article.
        Replaces the LLM topic+script steps with RSS fetch + summarization;
        all downstream steps (images, TTS, combine) are unchanged.

        Args:
            tts_instance (TTS): Instance of TTS Class.

        Returns:
            path (str): The path to the generated MP4 file.
        """
        # Fetch article and generate script from it
        self.fetch_news_article()
        self.generate_news_script()

        # Shared downstream pipeline
        self.generate_metadata()
        # Append the original article URL to the description so viewers can read the full story
        self.metadata["description"] += f"\n\nFull story: {self.article['url']}"

        self.generate_prompts()

        for i, prompt in enumerate(self.image_prompts):
            if i > 0:
                time.sleep(20)
            self.generate_image(prompt)

        if not self.images:
            raise RuntimeError("Image generation failed for all prompts. Check Gemini API key and rate limits.")

        self.generate_script_to_speech(tts_instance)

        path = self.combine()

        if get_verbose():
            info(f" => Generated News Video: {path}")

        self.video_path = os.path.abspath(path)

        return path

    def _init_browser(self) -> None:
        """Kills orphaned geckodriver processes, clears profile locks, then opens browser."""
        import subprocess
        # Kill any leftover geckodriver processes from previous crashed runs
        # (does NOT kill firefox.exe to avoid closing the user's personal browser)
        subprocess.call(["taskkill", "/f", "/im", "geckodriver.exe"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        clear_firefox_profile_lock(self._fp_profile_path)
        service = Service(GeckoDriverManager().install())
        self.browser = webdriver.Firefox(service=service, options=self.options)

    def get_channel_id(self) -> str:
        """
        Gets the Channel ID of the YouTube Account.

        Returns:
            channel_id (str): The Channel ID.
        """
        self._init_browser()
        driver = self.browser
        driver.get("https://studio.youtube.com")
        time.sleep(2)
        channel_id = driver.current_url.split("/")[-1]
        self.channel_id = channel_id

        return channel_id

    def upload_video(self) -> bool:
        """
        Uploads the video to YouTube.

        Returns:
            success (bool): Whether the upload was successful or not.
        """
        try:
            self.get_channel_id()

            driver = self.browser
            verbose = get_verbose()

            # Go to youtube.com/upload
            driver.get("https://www.youtube.com/upload")

            # Set video file
            FILE_PICKER_TAG = "ytcp-uploads-file-picker"
            file_picker = driver.find_element(By.TAG_NAME, FILE_PICKER_TAG)
            INPUT_TAG = "input"
            file_input = file_picker.find_element(By.TAG_NAME, INPUT_TAG)
            file_input.send_keys(self.video_path)

            # Wait for upload to finish
            time.sleep(5)

            # Set title
            textboxes = driver.find_elements(By.ID, YOUTUBE_TEXTBOX_ID)

            title_el = textboxes[0]
            description_el = textboxes[-1]

            if verbose:
                info("\t=> Setting title...")

            title_el.click()
            time.sleep(1)
            title_el.send_keys(Keys.CONTROL + "a")
            title_el.send_keys(Keys.DELETE)
            title_el.send_keys(self.metadata["title"])

            if verbose:
                info("\t=> Setting description...")

            # Set description via clipboard paste — send_keys truncates long text
            # Re-fetch to avoid stale element reference after title interaction
            import pyperclip
            time.sleep(10)
            description_el = driver.find_elements(By.ID, YOUTUBE_TEXTBOX_ID)[-1]
            description_el.click()
            time.sleep(0.5)
            description_el.send_keys(Keys.CONTROL + "a")
            description_el.send_keys(Keys.DELETE)
            pyperclip.copy(self.metadata["description"])
            description_el.send_keys(Keys.CONTROL + "v")

            time.sleep(0.5)

            # Set `made for kids` option
            if verbose:
                info("\t=> Setting `made for kids` option...")

            is_for_kids_checkbox = driver.find_element(
                By.NAME, YOUTUBE_MADE_FOR_KIDS_NAME
            )
            is_not_for_kids_checkbox = driver.find_element(
                By.NAME, YOUTUBE_NOT_MADE_FOR_KIDS_NAME
            )

            if not get_is_for_kids():
                is_not_for_kids_checkbox.click()
            else:
                is_for_kids_checkbox.click()

            time.sleep(0.5)

            # Click next
            if verbose:
                info("\t=> Clicking next...")

            next_button = driver.find_element(By.ID, YOUTUBE_NEXT_BUTTON_ID)
            next_button.click()

            # Click next again
            if verbose:
                info("\t=> Clicking next again...")
            next_button = driver.find_element(By.ID, YOUTUBE_NEXT_BUTTON_ID)
            next_button.click()

            # Wait for 2 seconds
            time.sleep(2)

            # Click next again
            if verbose:
                info("\t=> Clicking next again...")
            next_button = driver.find_element(By.ID, YOUTUBE_NEXT_BUTTON_ID)
            next_button.click()

            # Set as unlisted
            if verbose:
                info("\t=> Setting as unlisted...")

            radio_button = driver.find_elements(By.XPATH, YOUTUBE_RADIO_BUTTON_XPATH)
            radio_button[2].click()

            if verbose:
                info("\t=> Clicking done button...")

            # Click done button
            done_button = driver.find_element(By.ID, YOUTUBE_DONE_BUTTON_ID)
            done_button.click()

            # Wait for 2 seconds
            time.sleep(2)

            # Get latest video
            if verbose:
                info("\t=> Getting video URL...")

            # Get the latest uploaded video URL
            driver.get(
                f"https://studio.youtube.com/channel/{self.channel_id}/videos/short"
            )
            time.sleep(2)
            videos = driver.find_elements(By.TAG_NAME, "ytcp-video-row")
            first_video = videos[0]
            anchor_tag = first_video.find_element(By.TAG_NAME, "a")
            href = anchor_tag.get_attribute("href")
            if verbose:
                info(f"\t=> Extracting video ID from URL: {href}")
            video_id = href.split("/")[-2]

            # Build URL
            url = build_url(video_id)

            self.uploaded_video_url = url

            if verbose:
                success(f" => Uploaded Video: {url}")

            # Add video to cache
            self.add_video(
                {
                    "title": self.metadata["title"],
                    "description": self.metadata["description"],
                    "url": url,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

            # Close the browser
            driver.quit()

            return True
        except Exception as e:
            error(f"upload_video failed: {type(e).__name__}: {e}")
            if self.browser is not None:
                self.browser.quit()
            return False

    def get_videos(self) -> List[dict]:
        """
        Gets the uploaded videos from the YouTube Channel.

        Returns:
            videos (List[dict]): The uploaded videos.
        """
        if not os.path.exists(get_youtube_cache_path()):
            # Create the cache file
            with open(get_youtube_cache_path(), "w") as file:
                json.dump({"videos": []}, file, indent=4)
            return []

        videos = []
        # Read the cache file
        with open(get_youtube_cache_path(), "r") as file:
            previous_json = json.loads(file.read())
            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    videos = account["videos"]

        return videos
