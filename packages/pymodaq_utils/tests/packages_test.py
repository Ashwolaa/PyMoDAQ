from pymodaq_utils.packages import extract_authors_from_description


def test_no_instruments_with_contributors():
    desc = "Authors\n=======\n\n* Alice Martin\n* Bob Smith\n\nContributors\n============\n\n* Carol Jones"
    assert extract_authors_from_description(desc) == ["Alice Martin", "Bob Smith"]


def test_no_instruments_no_contributors_keeps_last_char():
    desc = "Authors\n=======\n\n* Alice Martin\n* Bob Smith"
    assert extract_authors_from_description(desc) == ["Alice Martin", "Bob Smith"]


def test_long_author_list_not_truncated():
    names = ["Author Number %02d Longname" % i for i in range(8)]
    desc = "Authors\n=======\n\n" + "\n".join("* " + n for n in names)
    assert len(desc) > 100
    assert extract_authors_from_description(desc) == names


def test_with_instruments_marker():
    desc = "Authors\n=======\n\n* Alice Martin\n* Bob Smith\n\nInstruments\n===========\n\n* Camera"
    assert extract_authors_from_description(desc) == ["Alice Martin", "Bob Smith"]
