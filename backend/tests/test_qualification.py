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


def test_rejects_startup_directories_and_listicles():
    # directory domains
    assert deterministic_reject(_c("Startups in United States", "https://tracxn.com/x", "tracxn.com"))
    assert deterministic_reject(_c("X", "https://growthlist.co/x", "growthlist.co"))
    # listicle titles (these slipped through before)
    assert deterministic_reject(_c("Top Series B Startups 2026", "https://x.io/p", "x.io"))
    assert deterministic_reject(_c("11,130+ Series A Startups & Funding List 2026", "https://x.co/p", "x.co"))
    assert deterministic_reject(_c("Best Startups with Recent Funding in 2026", "https://x.co/p", "x.co"))
    assert deterministic_reject(_c("Seven ways to finance your tech startup", "https://x.com/p", "x.com"))


def test_rejects_job_and_content_subdomains():
    assert deterministic_reject(_c("Director of Eng", "https://jobs.scotiabank.com/x", "jobs.scotiabank.com"))
    assert deterministic_reject(_c("Ratings", "https://careers.morningstar.com/x", "careers.morningstar.com"))
    assert deterministic_reject(_c("Post", "https://blog.acme.com/x", "blog.acme.com"))
    # but the apex domain is fine
    assert deterministic_reject(_c("Morningstar", "https://morningstar.com", "morningstar.com")) is None


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


def test_does_not_reject_real_companies_false_positives():
    """Regression guard from the adversarial review: high-precision filter must
    NOT kill real companies whose names/taglines contain common content words."""
    keep = [
        # bare 'guide' must survive
        _c("Insurance Guide Inc", "https://insguide.com", "insguide.com"),
        _c("Guidewire", "https://guidewire.com", "guidewire.com"),
        # "<noun> for/to" SaaS taglines must survive
        _c("Gusto - Payroll Software for Small Businesses", "https://gusto.com", "gusto.com"),
        _c("Cloudflare - Tools for Developers", "https://cloudflare.com", "cloudflare.com"),
        _c("Salesforce - CRM Software for Sales Teams", "https://salesforce.com", "salesforce.com"),
        # apex domains equal to a junk label must survive
        _c("Help.com", "https://help.com", "help.com"),
        _c("Status", "https://status.io", "status.io"),
        # brand names with job/career/news/pricing tokens
        _c("Jobs for Humanity", "https://jobsforhumanity.com", "jobsforhumanity.com"),
        _c("Hiring Lab", "https://hiringlab.org", "hiringlab.org"),
        _c("Newsela", "https://newsela.com", "newsela.com"),
        # long SEO homepage tagline (brand portion is short)
        _c("Notion - The all-in-one workspace that brings your notes docs projects and team wikis together",
           "https://notion.so", "notion.so"),
    ]
    for c in keep:
        assert deterministic_reject(c) is None, f"wrongly rejected: {c.title}"
