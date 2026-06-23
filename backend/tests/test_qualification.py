from app.ai.qualification_engine import Candidate, _clean_title, deterministic_reject


def _c(title, url, domain):
    return Candidate(title=title, url=url, domain=domain, snippet="", source="tavily")


def test_rejects_blog_and_listicle_titles():
    assert deterministic_reject(_c("What is Contract Automation?", "https://x.com/blog/a", "x.com"))
    assert deterministic_reject(_c("Top 5 CFO Companies 2026", "https://x.com/p", "x.com"))
    assert deterministic_reject(_c("Best Fractional CFO Services", "https://x.com/p", "x.com"))
    assert deterministic_reject(_c("How to hire a CFO", "https://x.com/p", "x.com"))


def test_rejects_job_boards_and_directories():
    assert deterministic_reject(_c("Acme", "https://ziprecruiter.com/j", "ziprecruiter.com"))
    assert deterministic_reject(_c("Acme", "https://g2.com/x", "g2.com"))
    assert deterministic_reject(_c("Acme", "https://ycombinator.com/x", "ycombinator.com"))


def test_rejects_content_paths():
    assert deterministic_reject(_c("Acme", "https://acme.com/blog/post", "acme.com"))
    assert deterministic_reject(_c("Acme", "https://acme.com/news/x", "acme.com"))


def test_accepts_real_company_homepages():
    assert deterministic_reject(_c("Ironclad", "https://ironcladapp.com", "ironcladapp.com")) is None
    assert deterministic_reject(_c("NowCFO - Fractional CFO", "https://nowcfo.com", "nowcfo.com")) is None


def test_clean_title():
    assert _clean_title("NowCFO - Fractional CFO Services") == "NowCFO"
    assert _clean_title("Aleph | Finance OS") == "Aleph"
    assert _clean_title("Ironclad") == "Ironclad"
