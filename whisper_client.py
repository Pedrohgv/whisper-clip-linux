from faster_whisper import WhisperModel
import os

# flag to control deleting of newly created files
DELETE_FILE_AFTER_TRANSCRIPTION = os.getenv("DELETE_FILE_AFTER_TRANSCRIPTION", 'true').lower() == 'true'

class WhisperClient:
    def __init__(self, model_name="medium.en"):
        self.model_name = model_name
        self.model = None

    def load_model(self):
        if self.model is None:
            # self.model = whisper.load_model(self.model_name)
            self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")

    def unload_model(self):
        if self.model is not None:
            # Clear CUDA cache
            # if torch.cuda.is_available():
            #     torch.cuda.empty_cache()
            
            # Delete model and clear from memory
            del self.model
            self.model = None
            
            # Force garbage collection
            import gc
            gc.collect()
            # if torch.cuda.is_available():
            #     torch.cuda.empty_cache()

    def transcribe(self, audio_path):
        if self.model is None:
            self.load_model()
        # result = self.model.transcribe(audio_path)
        segments, info = self.model.transcribe(audio_path, beam_size=5)

        text = ""
        for segment in segments:
            text = text + segment.text
    
        # delete file if flag is set
        if DELETE_FILE_AFTER_TRANSCRIPTION:
            os.remove(audio_path)

        # return result["text"]
        return text
