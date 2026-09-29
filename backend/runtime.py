"""Process-wide singletons. Models are loaded exactly once, here, at import."""
import pipeline
from services.jobs import JobManager

ai_pipeline = pipeline.AIVideoPipeline()
jobs = JobManager(ai_pipeline)
