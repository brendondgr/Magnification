"""
Fast skill extraction + profile skill matching.

The default extractor is a deterministic **gazetteer matcher** (no LLM, no network):
it scans a job description for skills drawn from a base technical vocabulary plus the
active profile's own skills. An optional LLM extractor is available for richer results,
gated by the runtime config (`enable_llm_skills`).
"""

import re
from typing import Any, Dict, List, Optional

# A compact base vocabulary of common skills. The profile's own skills are merged in at
# call time, so the most important terms are always the user's. Multi-word terms are
# matched as phrases; short tokens are matched on token boundaries.
BASE_SKILLS: List[str] = [
    # languages
    "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust", "Ruby",
    "Scala", "Kotlin", "Swift", "R", "MATLAB", "SQL", "Bash", "PHP",
    # web / backend
    "React", "Vue", "Angular", "Node.js", "Flask", "Django", "FastAPI", "Spring",
    "GraphQL", "REST", "HTML", "CSS", "Tailwind",
    # data / ML
    "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "PyTorch",
    "TensorFlow", "Keras", "Scikit-learn", "Pandas", "NumPy", "Spark", "Hadoop",
    "Data Science", "Statistics", "Reinforcement Learning", "LLM", "RAG",
    "Transformers", "Hugging Face", "XGBoost", "MLOps",
    # cloud / infra / devops
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "CI/CD", "Git",
    "Linux", "Airflow", "Kafka", "Redis", "PostgreSQL", "MongoDB", "Elasticsearch",
    # domains
    "Healthcare", "Finance", "Bioinformatics", "Robotics", "Cybersecurity",
    "Embedded Systems", "Quantitative", "Agentic AI",
]

# Characters kept when normalizing text so skills like "c++", "node.js", "ci/cd" survive.
_KEEP = re.compile(r"[^a-z0-9+#./ -]")


def _normalize(term: str) -> str:
    return term.strip().lower()


def _clean_text(text: str) -> str:
    return " " + _KEEP.sub(" ", (text or "").lower()) + " "


def extract_skills(text: str,
                   extra_skills: Optional[List[str]] = None,
                   gazetteer: Optional[List[str]] = None) -> List[str]:
    """
    Return the skills (from the gazetteer + extra_skills) that appear in ``text``.

    Matching is case-insensitive and boundary-aware so "Java" does not match
    "JavaScript". Returns the original-cased term, de-duplicated, sorted.
    """
    cleaned = _clean_text(text)
    # Map normalized -> display term; profile skills win the display casing.
    terms: Dict[str, str] = {}
    for t in (gazetteer if gazetteer is not None else BASE_SKILLS):
        terms.setdefault(_normalize(t), t)
    for t in (extra_skills or []):
        if t and t.strip():
            terms[_normalize(t)] = t.strip()

    found = []
    for norm, display in terms.items():
        if not norm:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])"
        if re.search(pattern, cleaned):
            found.append(display)
    return sorted(set(found), key=str.lower)


def match_profile_skills(job_skills: List[str],
                         profile_skills: List[str]) -> Dict[str, Any]:
    """
    Compare a job's skills against the profile's skills.

    Returns ``{matched, missing, score}`` where ``matched`` are job skills the user has,
    ``missing`` are job skills the user lacks, and ``score`` is the fraction of the job's
    skills the user covers (0..1; 0 when the job lists no skills).
    """
    pset = {_normalize(s) for s in (profile_skills or [])}
    matched = [s for s in (job_skills or []) if _normalize(s) in pset]
    missing = [s for s in (job_skills or []) if _normalize(s) not in pset]
    score = (len(matched) / len(job_skills)) if job_skills else 0.0
    return {"matched": matched, "missing": missing, "score": round(score, 4)}


LLM_SKILLS_PROMPT = (
    "Extract the concrete technical/professional skills explicitly required or mentioned "
    "in the job description below. Respond with ONLY a JSON array of short skill strings "
    "(no prose, no code fences)."
)


def extract_skills_llm(text: str, client) -> List[str]:
    """
    Extract skills with the LLM (richer than the gazetteer). ``client`` is any object with
    ``chat_json``. Returns a list of skill strings; raises on call/parse failure so the
    caller can fall back to the gazetteer.
    """
    messages = [
        {"role": "system", "content": LLM_SKILLS_PROMPT},
        {"role": "user", "content": text},
    ]
    raw = client.chat_json(messages)
    if isinstance(raw, dict):  # tolerate {"skills": [...]}
        raw = raw.get("skills", [])
    if not isinstance(raw, list):
        return []
    # De-duplicate case-insensitively, keeping the first-seen casing and order.
    seen = set()
    out = []
    for item in raw:
        s = str(item).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out
