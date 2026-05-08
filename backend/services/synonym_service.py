"""
Skill Synonyms Service — Maps common skill variations to canonical forms.
Used by search to expand queries for better recall.
"""

# Bidirectional synonym groups — searching any term finds all related terms
SYNONYM_GROUPS = [
    # Programming Languages
    ["java", "j2ee", "core java", "java 8", "java 11", "java 17"],
    ["python", "python3", "python 3"],
    ["javascript", "js", "ecmascript", "es6"],
    ["typescript", "ts"],
    ["c#", "csharp", "c sharp", ".net", "dotnet"],
    ["c++", "cpp"],
    ["golang", "go lang", "go"],

    # Frontend
    ["react", "reactjs", "react.js", "react js"],
    ["angular", "angularjs", "angular.js"],
    ["vue", "vuejs", "vue.js", "vue js"],
    ["next.js", "nextjs", "next js"],
    ["nuxt", "nuxtjs", "nuxt.js"],

    # Backend
    ["spring boot", "springboot", "spring-boot", "spring framework"],
    ["node", "nodejs", "node.js", "node js"],
    ["django", "django rest", "drf"],
    ["express", "expressjs", "express.js"],
    ["fastapi", "fast api"],
    ["flask", "python flask"],

    # DevOps / Cloud
    ["aws", "amazon web services", "amazon cloud"],
    ["azure", "microsoft azure", "ms azure"],
    ["gcp", "google cloud", "google cloud platform"],
    ["kubernetes", "k8s", "kube"],
    ["docker", "containerization", "containers"],
    ["ci/cd", "cicd", "ci cd", "continuous integration", "continuous deployment"],
    ["terraform", "iac", "infrastructure as code"],

    # Data
    ["sql", "mysql", "postgresql", "postgres", "sql server", "mssql"],
    ["mongodb", "mongo", "nosql"],
    ["redis", "in-memory cache"],
    ["kafka", "apache kafka", "event streaming"],
    ["spark", "apache spark", "pyspark"],
    ["hadoop", "hdfs", "mapreduce"],
    ["power bi", "powerbi"],
    ["tableau", "data visualization"],

    # HR / Functional
    ["hr", "human resources", "human resource"],
    ["hrbp", "hr business partner"],
    ["talent acquisition", "ta", "recruitment", "recruiting"],
    ["payroll", "salary processing", "payroll management"],
    ["statutory compliance", "pf", "esi", "gratuity", "labour laws"],
    ["performance management", "pms", "appraisal"],

    # Finance
    ["ca", "chartered accountant", "icai"],
    ["cfa", "chartered financial analyst"],
    ["accounts", "accounting", "accountancy"],
    ["gst", "goods and services tax"],
    ["tds", "tax deducted at source"],
    ["sap fico", "sap fi", "sap co"],

    # Sales / Marketing
    ["sales", "business development", "bd"],
    ["digital marketing", "online marketing", "internet marketing"],
    ["seo", "search engine optimization"],
    ["sem", "search engine marketing", "ppc", "google ads"],
    ["crm", "customer relationship management", "salesforce crm"],

    # Project Management
    ["pmp", "project management professional"],
    ["agile", "scrum", "kanban"],
    ["scrum master", "csm", "psm"],
    ["jira", "atlassian jira"],

    # Testing
    ["qa", "quality assurance", "testing"],
    ["selenium", "test automation", "automation testing"],
    ["manual testing", "functional testing"],

    # Mobile
    ["android", "android development", "android studio"],
    ["ios", "ios development", "swift", "objective-c"],
    ["flutter", "dart"],
    ["react native", "rn"],

    # Designations
    ["swe", "software engineer", "software developer"],
    ["sde", "software development engineer"],
    ["tech lead", "technical lead", "engineering lead"],
    ["vp", "vice president"],
    ["avp", "assistant vice president"],
    ["manager", "mgr"],
    ["director", "dir"],
]

# Build lookup dict
_SYNONYM_MAP = {}
for group in SYNONYM_GROUPS:
    normalized = [s.lower().strip() for s in group]
    for term in normalized:
        _SYNONYM_MAP[term] = normalized


def expand_query(query: str) -> list:
    """
    Expand a search query with synonyms.
    Input: "react developer with k8s"
    Output: ["react", "reactjs", "react.js", "react js", "developer", "k8s", "kubernetes", "kube"]
    """
    words = query.lower().strip().split()
    expanded = set()

    # Try multi-word matches first (longest match)
    i = 0
    while i < len(words):
        matched = False
        # Try 3-word, 2-word, then 1-word
        for n in [3, 2, 1]:
            if i + n <= len(words):
                phrase = " ".join(words[i:i+n])
                if phrase in _SYNONYM_MAP:
                    expanded.update(_SYNONYM_MAP[phrase])
                    i += n
                    matched = True
                    break
        if not matched:
            expanded.add(words[i])
            i += 1

    return list(expanded)


def get_synonym_regex(query: str) -> str:
    """
    Build a MongoDB regex pattern that matches any synonym.
    Input: "react"
    Output: "react|reactjs|react\\.js|react js"
    """
    import re
    expanded = expand_query(query)
    escaped = [re.escape(t) for t in expanded]
    return "|".join(escaped)
