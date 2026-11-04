"""품질 필터. 왜 제외했는지 항상 사유로 남긴다."""

import re
from collections import defaultdict
from collections.abc import Mapping

from collector.domain.models import ExclusionReason, Repository, SkillRecord

_TOKEN_SPLIT = re.compile(r"[-_.]+")
_CODE = re.compile(r"(`{3,}|~{3,}).*?\1|`[^`\n]*`", re.DOTALL)
_HAN_OR_KANA = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_HANGUL = re.compile(r"[\uac00-\ud7a3]")
_LATIN = re.compile(r"[A-Za-z]")
# 한자·가나·한글 한 글자는 로마자 서너 글자만큼의 뜻을 담는다.
# 글자 수를 그대로 세면 한자 비중이 작게 나온다.
_IDEOGRAM_WEIGHT = 3
FOREIGN_SHARE = 0.5
# 라틴 문자를 쓰는 다른 언어는 글자로 가를 수 없어 자주 쓰는 기능어를 센다 (ADR-0021).
# 낱말 목록은 영어와 겹치지 않는 것만 골랐다. 표본 156개에서 영어 스킬을 잘못 거른 적이 없다.
_WORD = re.compile(r"[a-zà-ÿœ]+", re.IGNORECASE)
_ENGLISH_WORDS = frozenset(
    "the and of to is for with that this you are be on or it as from your when use".split()
)
_OTHER_LATIN_WORDS = {
    "fr": frozenset(
        "les des est pour une dans avec sur pas aux cette vous sont être du qui leur mais".split()
    ),
    "de": frozenset(
        "der die das und ist nicht mit für eine den dem wird oder auch sich auf werden bei".split()
    ),
    "es": frozenset(
        "los las del para con una por como pero más esta este sus también puede según".split()
    ),
    "pt": frozenset("os do da não uma com para são mais também pelo pela você seu sua".split()),
    "it": frozenset("il gli della delle degli per non sono anche questo questa nel alla".split()),
}
_VIETNAMESE = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", re.IGNORECASE)
# 베트남어 한 낱말에는 성조 표시가 대개 하나 이상 붙는다. 기능어 하나와 비슷한 무게로 센다.
_VIETNAMESE_MARKS_PER_WORD = 4
MIN_FOREIGN_WORDS = 15
_FILLER_TOKENS = {"agent", "agents", "claude", "code", "my", "repo", "skill", "skills"}
_TEST_TOKENS = {
    "demo",
    "demos",
    "example",
    "examples",
    "playground",
    "sample",
    "samples",
    "sandbox",
    "temp",
    "test",
    "testing",
    "tests",
    "tmp",
}
_TEST_DIRECTORIES = {
    "__tests__",
    "fixtures",
    "node_modules",
    "template",
    "templates",
    "test",
    "testdata",
    "tests",
}


def repository_exclusion(repository: Repository) -> ExclusionReason | None:
    if repository.is_fork:
        return ExclusionReason.FORK
    if _is_test_repository(repository.name):
        return ExclusionReason.TEST_REPOSITORY
    return None


def _is_test_repository(name: str) -> bool:
    """`test-automation-skills`는 남기고 `claude-skill-test`만 걸러낸다."""
    tokens = {token for token in _TOKEN_SPLIT.split(name.lower()) if token}
    meaningful = tokens - _FILLER_TOKENS
    return bool(meaningful) and meaningful <= _TEST_TOKENS


def path_exclusion(path: str) -> ExclusionReason | None:
    directories = path.lower().split("/")[:-1]
    if _TEST_DIRECTORIES.intersection(directories):
        return ExclusionReason.TEST_PATH
    return None


def content_exclusion(body: str, min_chars: int) -> ExclusionReason | None:
    if not body.strip():
        return ExclusionReason.EMPTY
    if len(body.strip()) < min_chars:
        return ExclusionReason.TOO_SHORT
    return language_exclusion(body)


def language_exclusion(body: str) -> ExclusionReason | None:
    """본문의 절반 이상이 한자·가나이면 제외한다. 코드는 세지 않는다.

    영어 스킬에 중국어 예시가 조금 섞인 경우는 남는다.
    """
    prose = _CODE.sub(" ", body)
    foreign = len(_HAN_OR_KANA.findall(prose)) * _IDEOGRAM_WEIGHT
    readable = len(_HANGUL.findall(prose)) * _IDEOGRAM_WEIGHT + len(_LATIN.findall(prose))
    if foreign and foreign >= (foreign + readable) * FOREIGN_SHARE:
        return ExclusionReason.FOREIGN_LANGUAGE
    if _mostly_other_latin_language(prose):
        return ExclusionReason.FOREIGN_LANGUAGE
    return None


def _mostly_other_latin_language(prose: str) -> bool:
    """프랑스어, 독일어, 스페인어 같은 본문을 거른다 (ADR-0021).

    한 나라의 법률·세무 스킬은 대개 그 나라 말로 쓰여 있다. 영어 스킬에 외국어 낱말이
    조금 섞인 경우는 영어 기능어가 더 많아서 남는다.
    """
    words = [word.lower() for word in _WORD.findall(prose)]
    english = sum(1 for word in words if word in _ENGLISH_WORDS)
    other = max(sum(1 for word in words if word in vocab) for vocab in _OTHER_LATIN_WORDS.values())
    vietnamese = len(_VIETNAMESE.findall(prose)) // _VIETNAMESE_MARKS_PER_WORD
    foreign = max(other, vietnamese)
    return foreign >= MIN_FOREIGN_WORDS and foreign > english


def mark_duplicates(
    skills: Mapping[str, SkillRecord], stars: Mapping[str, int]
) -> dict[str, SkillRecord]:
    """같은 내용과, 한 저장소 안의 같은 이름을 하나만 남긴다.

    내용이 같으면 스타가 가장 많은 저장소를 고른다. 플랫폼별 사본처럼 한 저장소에 같은 이름이
    여럿이면 경로가 가장 얕은 스킬을 고른다. 다른 사유로 제외된 스킬은 후보가 될 수 없고,
    원본이 사라지면 다시 계산되도록 기존 DUPLICATE 표시는 매번 새로 정한다.
    """
    by_hash: defaultdict[str, list[str]] = defaultdict(list)
    for key, skill in skills.items():
        if skill.exclusion in (None, ExclusionReason.DUPLICATE):
            by_hash[skill.skill_md_hash].append(key)
    content_winners = [
        min(keys, key=lambda key: (-stars.get(skills[key].repository, 0), key))
        for keys in by_hash.values()
    ]

    by_name: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for key in content_winners:
        skill = skills[key]
        by_name[skill.repository, skill.name.lower()].append(key)
    winners = {
        min(keys, key=lambda key: (skills[key].path.count("/"), key)) for keys in by_name.values()
    }

    marked = dict(skills)
    for keys in by_hash.values():
        for key in keys:
            exclusion = None if key in winners else ExclusionReason.DUPLICATE
            if skills[key].exclusion != exclusion:
                marked[key] = skills[key].model_copy(update={"exclusion": exclusion})
    return marked
