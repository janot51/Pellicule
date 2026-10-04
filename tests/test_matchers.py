from pellicule.policy.matchers import glob_path_match


def test_glob_double_star_cross_dirs():
    assert glob_path_match("sources/**/*.pdf", "sources/a/b.pdf")
    assert glob_path_match("sources/**/*.pdf", "sources/note.pdf")
    assert not glob_path_match("sources/**/*.pdf", "other/a.pdf")


def test_glob_single_star_segment():
    assert glob_path_match("analysis/**", "analysis/foo.py")
    assert not glob_path_match("analysis/**", "output/foo.py")
