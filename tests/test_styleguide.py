from django.template import Context, Template


def test_styleguide_is_hidden_unless_debug(client_in):
    assert client_in.get("/_styleguide/").status_code == 404


def test_styleguide_shows_in_debug(client_in, settings):
    settings.DEBUG = True
    res = client_in.get("/_styleguide/")
    assert res.status_code == 200
    html = res.content.decode()
    assert "css/tokens.css" in html and "css/components.css" in html


def test_icon_tag_points_at_the_sprite():
    html = Template('{% load kairos %}{% icon "pipeline" %}').render(Context())
    assert 'class="i"' in html and "icons/sprite.svg#pipeline" in html
    assert 'aria-hidden="true"' in html


def test_icon_tag_takes_a_size():
    html = Template('{% load kairos %}{% icon "plus" "16" %}').render(Context())
    assert 'class="i i-16"' in html


def test_every_styleguide_icon_is_in_the_sprite():
    from pathlib import Path

    from django.conf import settings as dj

    from apps.core.views import STYLEGUIDE_ICONS

    sprite = (Path(dj.BASE_DIR) / "static/icons/sprite.svg").read_text()
    missing = [name for name in STYLEGUIDE_ICONS if f'id="{name}"' not in sprite]
    assert missing == []
