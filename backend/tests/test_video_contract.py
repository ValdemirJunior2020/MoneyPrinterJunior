from app.services import video

# This is the backend service contract expected by the application pipeline/UI API layer.
REQUIRED_VIDEO_FUNCTIONS = [
    'probe_duration',
    'prepare_visual_clip',
    'assemble_visuals',
    'render_video',
    'ken_burns_filter',
    'safe_media_path',
    'build_srt',
]


def test_video_service_contract_exists():
    missing = [name for name in REQUIRED_VIDEO_FUNCTIONS if not hasattr(video, name)]
    assert missing == []
