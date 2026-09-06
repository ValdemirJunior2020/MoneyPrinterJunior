from app.schemas import Scene, ScenePlan, SubtitleSettings
from app.services.subtitles import build_srt


def test_subtitles_use_scene_timeline(tmp_path):
    plan = ScenePlan(title='t', target_duration_seconds=10, scenes=[
        Scene(scene_number=1, narration='Faith begins here.', search_query='faith art', alternate_query='church light', visual_type='art', estimated_seconds=4),
        Scene(scene_number=2, narration='Then the journey continues with hope.', search_query='journey road', alternate_query='sunrise path', visual_type='landscape', estimated_seconds=6),
    ])
    output = tmp_path / 'subs.srt'
    build_srt(plan, [4.0, 6.0], SubtitleSettings(mode='sentence'), output)
    text = output.read_text()
    assert '00:00:00,000 --> 00:00:04,000' in text
    assert '00:00:04,000 --> 00:00:10,000' in text
