"""Process-wide singletons. Models are loaded exactly once, here, at import."""
import pipeline
from services.jobs import JobManager
from services.live import LiveManager

ai_pipeline = pipeline.AIVideoPipeline()
jobs = JobManager(ai_pipeline)
live = LiveManager(ai_pipeline, jobs)
