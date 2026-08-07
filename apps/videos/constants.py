"""Shared constants for the analysis pipeline's progress tracking.

`UploadedVideo.pipeline_steps` is a JSONField keyed by these step names, each
mapped to one of the step-status strings below. Kept here (rather than
inline string literals scattered across apps) so every app's tasks.py agree
on the same vocabulary.
"""

PIPELINE_STEP_METADATA = "metadata"
PIPELINE_STEP_TRANSCRIPT = "transcript"
PIPELINE_STEP_SCENES = "scenes"
PIPELINE_STEP_ANALYSIS = "analysis"

ALL_PIPELINE_STEPS = [
    PIPELINE_STEP_METADATA,
    PIPELINE_STEP_TRANSCRIPT,
    PIPELINE_STEP_SCENES,
    PIPELINE_STEP_ANALYSIS,
]

STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_DONE = "done"
STEP_FAILED = "failed"
