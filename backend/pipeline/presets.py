"""
Role presets: data-driven scoring rubrics.

A preset describes how to score a resume for one role: a set of weighted
rubric dimensions plus toggles for optional enrichment steps. Presets are
plain data so they can move to the database in Phase 2; the seed presets
below double as the future DB seeds.
"""

from typing import Dict, List

from pydantic import BaseModel, Field, field_validator, model_validator


class EnrichmentToggles(BaseModel):
    """Optional pipeline steps a preset can switch on."""

    github: bool = False


class RubricDimension(BaseModel):
    """One scored dimension of a rubric."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    weight: float = Field(gt=0)
    guidance: str = Field(min_length=1, description="What good looks like")


class Preset(BaseModel):
    """A role's scoring configuration."""

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1)
    role_description: str = Field(min_length=1)
    dimensions: List[RubricDimension] = Field(min_length=1)
    enrichments: EnrichmentToggles = EnrichmentToggles()

    @model_validator(mode="after")
    def _unique_dimension_keys(self) -> "Preset":
        keys = [d.key for d in self.dimensions]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate dimension keys in preset '{self.id}'")
        return self

    def normalized_weights(self) -> Dict[str, float]:
        """Weights scaled to sum to 1.0, keyed by dimension key."""
        total = sum(d.weight for d in self.dimensions)
        return {d.key: d.weight / total for d in self.dimensions}


SEED_PRESETS: List[Preset] = [
    Preset(
        id="software-engineer",
        name="Software Engineer",
        role_description=(
            "An early engineer at a small, fast-moving startup. They will own "
            "features end-to-end across the stack with minimal supervision, so "
            "we care about evidence of building and shipping real things, not "
            "just coursework or credentials."
        ),
        enrichments=EnrichmentToggles(github=True),
        dimensions=[
            RubricDimension(
                key="technical_depth",
                name="Technical Depth",
                weight=30,
                guidance=(
                    "Breadth and depth of engineering skill: languages and "
                    "frameworks actually used in projects or work (not just "
                    "listed), systems knowledge, architectural complexity of "
                    "what they built. Solid full-stack competence scores well; "
                    "evidence of hard problems (concurrency, scale, infra, "
                    "novel algorithms) scores higher. A bare skills list with "
                    "no supporting evidence scores low."
                ),
            ),
            RubricDimension(
                key="shipped_projects",
                name="Shipped Projects",
                weight=25,
                guidance=(
                    "Personal or side projects that were actually finished and "
                    "shipped: live demos, real users, app-store listings, or "
                    "well-documented repos. Complex, original projects score "
                    "high. Tutorial-grade projects (todo apps, basic CRUD, "
                    "weather apps) score 0-2. Projects with no link, demo, or "
                    "repo to verify score at most 4."
                ),
            ),
            RubricDimension(
                key="open_source",
                name="Open Source Contributions",
                weight=15,
                guidance=(
                    "Contributions to projects the candidate does not own: "
                    "merged PRs to established projects, maintainership, GSoC "
                    "or similar programs. Personal repositories are NOT open "
                    "source contributions (they belong under Shipped Projects) "
                    "and score at most 3 here. If GitHub data is provided, "
                    "weigh 'open_source' project_type entries (multiple "
                    "contributors) above 'self_project' ones."
                ),
            ),
            RubricDimension(
                key="production_experience",
                name="Production Experience",
                weight=20,
                guidance=(
                    "Work, internship, or freelance experience where code ran "
                    "in production for real users: what they owned, what "
                    "shipped, measurable impact. Founder / early-startup "
                    "engineering experience is a strong positive signal."
                ),
            ),
            RubricDimension(
                key="startup_fit",
                name="Startup Fit",
                weight=10,
                guidance=(
                    "Signals of ownership, scrappiness, and speed: started "
                    "things (clubs, hackathons, products), wore multiple hats, "
                    "learned tools quickly, wrote publicly (blog, talks). "
                    "Evidence of self-direction scores well; a purely "
                    "credential-driven resume with no initiative signals "
                    "scores low."
                ),
            ),
        ],
    ),
    Preset(
        id="bd-intern",
        name="Business Development Intern",
        role_description=(
            "An intern who will do outbound outreach, qualify leads, support "
            "partnership conversations, and keep the pipeline organised at an "
            "early-stage startup. We care about communication, drive, and "
            "customer-facing evidence, not technical skills."
        ),
        dimensions=[
            RubricDimension(
                key="communication",
                name="Communication & Persuasion",
                weight=30,
                guidance=(
                    "Evidence of communicating and persuading: pitch "
                    "competitions, debate, presentations, public speaking, "
                    "writing (essays, newsletters, posts), or customer-facing "
                    "roles. The resume's own clarity and concision counts as "
                    "weak supporting evidence, not a substitute."
                ),
            ),
            RubricDimension(
                key="sales_experience",
                name="Sales / Partnership Exposure",
                weight=25,
                guidance=(
                    "Any experience touching revenue or partnerships: sales "
                    "or BD internships, fundraising or sponsorship for clubs "
                    "and events, retail or service jobs with targets, cold "
                    "outreach campaigns. Concrete numbers (deals closed, "
                    "sponsors signed, funds raised) score high; vague "
                    "'assisted the team' claims score low."
                ),
            ),
            RubricDimension(
                key="initiative",
                name="Initiative & Hustle",
                weight=25,
                guidance=(
                    "Started or led things: founded a club or society, ran a "
                    "side business, organised events, grew a community. "
                    "Leadership titles without described actions or outcomes "
                    "score low; self-started projects with visible outcomes "
                    "score high."
                ),
            ),
            RubricDimension(
                key="business_acumen",
                name="Business Acumen",
                weight=20,
                guidance=(
                    "Understanding of how businesses work: relevant "
                    "internships, case competitions, market research, "
                    "coursework applied to real problems, familiarity with "
                    "CRM or prospecting tools. Applied evidence beats listed "
                    "coursework."
                ),
            ),
        ],
    ),
    Preset(
        id="marketing-intern",
        name="Marketing Intern",
        role_description=(
            "An intern who will create content, run and measure campaigns, "
            "and grow audience for an early-stage startup. We care about "
            "demonstrated creation and measurable outcomes over theory."
        ),
        dimensions=[
            RubricDimension(
                key="content_creation",
                name="Content Creation",
                weight=30,
                guidance=(
                    "Things they actually made: social accounts or channels "
                    "they ran, blogs, videos, podcasts, design portfolios, "
                    "campaign assets. Linked, verifiable work scores high; "
                    "unlinked claims of 'managed social media' score mid at "
                    "best. Audience size and growth numbers strengthen the "
                    "evidence."
                ),
            ),
            RubricDimension(
                key="marketing_experience",
                name="Marketing Experience",
                weight=25,
                guidance=(
                    "Marketing internships, freelance work, or club/society "
                    "campaigns with described outcomes (reach, signups, "
                    "attendance, engagement). Measurable results score high; "
                    "responsibilities without outcomes score low."
                ),
            ),
            RubricDimension(
                key="analytics",
                name="Analytics & Tools",
                weight=20,
                guidance=(
                    "Evidence of measuring and iterating: A/B tests, SEO "
                    "work, ad campaigns with budgets and results, use of "
                    "tools like GA, Meta/Google Ads, Mailchimp, or basic data "
                    "analysis applied to marketing questions."
                ),
            ),
            RubricDimension(
                key="creativity_initiative",
                name="Creativity & Initiative",
                weight=25,
                guidance=(
                    "Original ideas executed without being asked: viral "
                    "moments, novel campaign angles, self-started projects, "
                    "brand or meme fluency appropriate to startup marketing. "
                    "Execution matters: an idea that shipped beats ten that "
                    "did not."
                ),
            ),
        ],
    ),
    Preset(
        id="product-designer",
        name="Product Designer",
        role_description=(
            "A designer who will own product design end-to-end at an "
            "early-stage startup: research, flows, UI, and working with "
            "engineers to ship. We care about shipped, verifiable design work "
            "and product judgment over tool lists or visual polish alone."
        ),
        dimensions=[
            RubricDimension(
                key="portfolio",
                name="Portfolio & Shipped Work",
                weight=35,
                guidance=(
                    "A linked, viewable portfolio of real work: case studies "
                    "that walk problem → exploration → shipped outcome, "
                    "products in production, app-store or web links. Case "
                    "studies with visible reasoning score high; dribbble-style "
                    "static shots without context score mid; an unlinked or "
                    "missing portfolio caps this dimension at 3 no matter "
                    "what the resume claims."
                ),
            ),
            RubricDimension(
                key="product_thinking",
                name="Product Thinking",
                weight=25,
                guidance=(
                    "Evidence of solving user and business problems, not just "
                    "drawing screens: user research, defining the problem, "
                    "iterating on feedback, measurable outcomes (conversion, "
                    "activation, retention, support-ticket drops). Design "
                    "decisions justified by evidence score high; purely "
                    "aesthetic descriptions score low."
                ),
            ),
            RubricDimension(
                key="craft",
                name="Interaction & Visual Craft",
                weight=20,
                guidance=(
                    "Quality of the work itself: interaction detail, "
                    "information hierarchy, design-system thinking "
                    "(components, tokens, consistency at scale), attention to "
                    "edge states (empty, error, loading). Tool lists (Figma, "
                    "etc.) count only when backed by work that shows mastery."
                ),
            ),
            RubricDimension(
                key="collaboration",
                name="Collaboration with Engineering",
                weight=10,
                guidance=(
                    "Evidence of shipping with engineers and PMs: handoff "
                    "quality, design QA, working within technical "
                    "constraints, contributing to or consuming a design "
                    "system, writing specs or documentation. Solo-only work "
                    "with no shipping partners scores low."
                ),
            ),
            RubricDimension(
                key="initiative",
                name="Initiative",
                weight=10,
                guidance=(
                    "Self-started design work: side projects, redesign "
                    "explorations with reasoning, community involvement, "
                    "writing or teaching about design. Shipped side projects "
                    "score higher than concept work."
                ),
            ),
        ],
    ),
    Preset(
        id="data-analyst",
        name="Data Analyst",
        role_description=(
            "An analyst who will own metrics, dashboards, and ad-hoc analysis "
            "at an early-stage startup: pull the data, answer the question, "
            "and change a decision. We care about end-to-end analyses with "
            "real impact over certificates and tool lists."
        ),
        enrichments=EnrichmentToggles(github=True),
        dimensions=[
            RubricDimension(
                key="analytical_projects",
                name="Analytical Projects",
                weight=30,
                guidance=(
                    "Real analyses carried end-to-end: a question, the data "
                    "wrangling, the method, and a conclusion someone could "
                    "act on — with verifiable artifacts (notebooks, "
                    "dashboards, reports, repos). Original analyses of real "
                    "or scraped data score high; tutorial-grade Kaggle "
                    "walkthroughs (Titanic, iris) score 1-3; projects with "
                    "no artifact to inspect score at most 4."
                ),
            ),
            RubricDimension(
                key="technical_toolkit",
                name="Technical Toolkit",
                weight=25,
                guidance=(
                    "SQL depth (joins, window functions, modeling), "
                    "Python/R for analysis (pandas, notebooks), statistics "
                    "fundamentals (distributions, significance, regression), "
                    "and dashboarding (Tableau, Looker, Metabase, or "
                    "similar) — evidenced through work and projects, not a "
                    "skills list. Spreadsheet mastery counts as real "
                    "evidence at the intern-to-junior level."
                ),
            ),
            RubricDimension(
                key="business_impact",
                name="Business Impact",
                weight=25,
                guidance=(
                    "Analyses that changed a decision: pricing, growth, "
                    "retention, ops efficiency — ideally quantified "
                    "('dashboard cut weekly reporting from 4h to 10min', "
                    "'churn analysis led to onboarding change, +8% "
                    "retention'). Working with stakeholders to scope the "
                    "question scores here too. Analysis for its own sake "
                    "with no decision attached scores low."
                ),
            ),
            RubricDimension(
                key="data_wrangling",
                name="Data Wrangling Pragmatism",
                weight=10,
                guidance=(
                    "Evidence of handling messy, real-world data: cleaning, "
                    "joining across systems, scraping or APIs, building "
                    "small pipelines, migrating spreadsheets into something "
                    "queryable. Clean-dataset-only experience scores mid at "
                    "best."
                ),
            ),
            RubricDimension(
                key="communication",
                name="Communication of Findings",
                weight=10,
                guidance=(
                    "Clear writing and visualization: reports or posts that "
                    "explain method and findings honestly, including "
                    "limitations and uncertainty. Charts that make the point "
                    "at a glance score high; jargon-heavy or overclaiming "
                    "writeups score low."
                ),
            ),
        ],
    ),
]

PRESETS_BY_ID: Dict[str, Preset] = {p.id: p for p in SEED_PRESETS}


def get_preset(preset_id: str) -> Preset:
    """Look up a seed preset by id, raising with the valid ids on miss."""
    try:
        return PRESETS_BY_ID[preset_id]
    except KeyError:
        valid = ", ".join(sorted(PRESETS_BY_ID))
        raise KeyError(f"Unknown preset '{preset_id}'. Available: {valid}") from None
