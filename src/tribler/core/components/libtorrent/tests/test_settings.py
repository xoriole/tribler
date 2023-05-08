from tribler.core.components.libtorrent.settings import TRIBLER_DOWNLOADS_DEFAULT, get_default_download_dir
from tribler.core.utilities.path_util import Path


def test_get_default_download_dir_exists(tmp_path, monkeypatch):
    # Test the case when the default download dir exists. Then it should be returned as is.
    # Historically, the default download dir was 'TriblerDownloads'
    monkeypatch.chdir(tmp_path)

    downloads = Path(TRIBLER_DOWNLOADS_DEFAULT)
    downloads.mkdir()

    actual = get_default_download_dir(home=Path("home"))
    assert actual == downloads.resolve()


def test_get_default_home_download_dir_exists(tmp_path, monkeypatch):
    # Test the case when the `$HOME/Downloads` dir exists. Then it should return default dir
    # as `$HOME/Downloads/TriblerDownloads`
    monkeypatch.chdir(tmp_path)

    home = Path("home")
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)

    download_dir = get_default_download_dir(home)
    assert download_dir == (downloads / TRIBLER_DOWNLOADS_DEFAULT).resolve()


def test_get_default_home_nothing_exists(tmp_path, monkeypatch):
    # Test the case when neither `$HOME/Downloads` nor `TriblerDownloads` dir exists.
    # Then it should return default dir as `$HOME/TriblerDownloads`
    monkeypatch.chdir(tmp_path)

    home = Path("home")

    download_dir = get_default_download_dir(home)
    assert download_dir == (home / TRIBLER_DOWNLOADS_DEFAULT).resolve()
