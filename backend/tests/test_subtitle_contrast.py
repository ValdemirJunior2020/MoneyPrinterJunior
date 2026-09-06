import pytest
from pydantic import ValidationError
from app.schemas import SubtitleSettings


def test_good_subtitle_contrast_is_allowed():
    SubtitleSettings(foreground_color='#FFFFFF', stroke_color='#000000', stroke_width=3)


def test_low_subtitle_contrast_is_rejected_without_background():
    with pytest.raises(ValidationError):
        SubtitleSettings(foreground_color='#FFFFFF', stroke_color='#EEEEEE', stroke_width=3, background=False)
