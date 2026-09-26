"""Unit tests for fuzzy scoring, matcher, and unified search index."""

import pytest
from astrarun.search.index import SearchIndex
from astrarun.search.matcher import FuzzyMatcher
from astrarun.search.models import CandidateCategory, SearchCandidate
from astrarun.search.scorer import FuzzyScorer, extract_acronym, is_subsequence


def test_acronym_extraction():
    assert extract_acronym("Visual Studio Code") == "vsc"
    assert extract_acronym("Windows Terminal") == "wt"
    assert extract_acronym("Google Chrome") == "gc"
    assert extract_acronym("Notepad") == "n"


def test_subsequence():
    assert is_subsequence("ntpd", "notepad")
    assert is_subsequence("dwnld", "downloads")
    assert not is_subsequence("xyz", "notepad")


def test_fuzzy_scorer_hierarchy():
    # Exact > Prefix > Token Prefix > Substring > Acronym > Subsequence > Typo
    score_exact = FuzzyScorer.score_single("notepad", "Notepad")
    score_prefix = FuzzyScorer.score_single("note", "Notepad")
    score_token = FuzzyScorer.score_single("code", "Visual Studio Code")
    score_sub = FuzzyScorer.score_single("term", "Windows Terminal")
    score_acronym = FuzzyScorer.score_single("vsc", "Visual Studio Code")
    score_subseq = FuzzyScorer.score_single("ntpd", "Notepad")
    score_typo = FuzzyScorer.score_single("notpad", "Notepad")
    score_unrelated = FuzzyScorer.score_single("asdfgh", "Notepad")

    assert score_exact == 1.0
    assert score_prefix >= 0.92
    assert score_token >= 0.88
    assert score_sub >= 0.82
    assert score_acronym >= 0.78
    assert score_subseq >= 0.60
    assert score_typo >= 0.60
    assert score_unrelated == 0.0


def test_usage_boost_bounded():
    # Usage boost should never exceed 0.04
    boost_0 = FuzzyScorer.compute_usage_boost(0, is_recent=False)
    boost_10 = FuzzyScorer.compute_usage_boost(10, is_recent=False)
    boost_1000 = FuzzyScorer.compute_usage_boost(1000, is_recent=True)

    assert boost_0 == 0.0
    assert 0.0 < boost_10 < 0.04
    assert boost_1000 <= 0.04


def test_textual_match_dominates_usage():
    # Even if Candidate B has 10,000 launches, typing Candidate A exactly must win
    matcher = FuzzyMatcher(min_score=0.45)
    cand_notepad = SearchCandidate(id="app:notepad", name="Notepad", category=CandidateCategory.APP, target="notepad.exe")
    cand_vivaldi = SearchCandidate(id="app:vivaldi", name="Vivaldi", category=CandidateCategory.APP, target="vivaldi.exe")

    # User frequently launches Vivaldi (10,000 launches)
    res_notepad = matcher.match_candidate("notepad", cand_notepad, launch_count=0)
    res_vivaldi = matcher.match_candidate("notepad", cand_vivaldi, launch_count=10000)

    assert res_notepad is not None
    assert res_notepad.score >= 0.99
    # Vivaldi should have zero textual match for "notepad" and be rejected
    assert res_vivaldi is None


def test_search_index_operations():
    index = SearchIndex()
    index.add(SearchCandidate(id="app:notepad", name="Notepad", category=CandidateCategory.APP, target="notepad.exe", aliases=["editor"]))
    index.add(SearchCandidate(id="app:calc", name="Calculator", category=CandidateCategory.APP, target="calc.exe", aliases=["calc"]))
    index.add(SearchCandidate(id="app:code", name="Visual Studio Code", category=CandidateCategory.APP, target="code.exe", aliases=["vscode", "code"]))
    index.add(SearchCandidate(id="folder:downloads", name="Downloads", category=CandidateCategory.FOLDER, target="C:\\Users\\hp\\Downloads"))

    # Test exact query
    r1 = index.search("notepad")
    assert len(r1) > 0
    assert r1[0].name == "Notepad"

    # Test alias
    r2 = index.search("editor")
    assert len(r2) > 0
    assert r2[0].name == "Notepad"

    # Test acronym
    r3 = index.search("vsc")
    assert len(r3) > 0
    assert r3[0].name == "Visual Studio Code"

    # Test typo tolerance
    r4 = index.search("notpad")
    assert len(r4) > 0
    assert r4[0].name == "Notepad"

    # Test typo on folder
    r5 = index.search("dwnloads")
    assert len(r5) > 0
    assert r5[0].name == "Downloads"

    # Test weak query rejected
    r6 = index.search("xyzunknown123")
    assert len(r6) == 0
