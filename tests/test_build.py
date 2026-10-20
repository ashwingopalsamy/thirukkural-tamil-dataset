from tkcore.build import load_tables, write_parquet


def test_parquet_is_byte_identical_across_builds(tmp_path):
    t = load_tables()
    write_parquet(t, tmp_path / "a")
    write_parquet(t, tmp_path / "b")
    for f in sorted((tmp_path / "a").iterdir()):
        assert f.read_bytes() == (tmp_path / "b" / f.name).read_bytes(), f.name
