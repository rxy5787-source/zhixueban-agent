import re
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

LEVELS = {'入门': 1, '基础': 1, '简单': 1, '容易': 1, '中等': 2, '适中': 2, '普通': 2,
          '提高': 3, '进阶': 3, '困难': 3, '较难': 3, '高': 3, '低': 1, '中': 2}
LEVEL_LABEL = '|'.join(LEVELS)
DIFFICULTY = re.compile(rf'难度\s*(?:为|是|[:：])?\s*({LEVEL_LABEL})(?![级文])|'
                        rf'({LEVEL_LABEL})\s*(?:难度|级别|题)')


def requested_difficulty(text):
    levels = {LEVELS[first or second] for first, second in DIFFICULTY.findall(text)}
    if len(levels) > 1:
        raise ValueError('本轮只能指定一个难度，请分开生成不同难度的题目')
    return next(iter(levels), 0)

class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=2000)

class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    fileIds: list[str] = Field(min_length=1, max_length=5)
    libraryName: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=80)
    points: list[Point] = Field(default_factory=list, max_length=12)
    questionCount: int = Field(default=3, ge=1, le=12)
    requirements: str = Field(default='',max_length=1200)
    difficulty: int = Field(default=0,ge=0,le=3)
    uploadWarnings: list[str] = Field(default_factory=list,max_length=5)

    requireModelGeneration: bool = False
    visionFallback: bool = False

    @field_validator('requirements')
    @classmethod
    def supported_type(cls,value):
        request=re.sub(r'(不要|不出|不需要|不含|不包含)(多选题?|填空题?|简答题?|问答题?|判断题?)','',value)
        if re.search(r'多选|填空|简答|问答题|判断题|证明题',request):raise ValueError('当前仅支持四选一单选题')
        return value

    @model_validator(mode='after')
    def resolve_difficulty(self):
        level = requested_difficulty(self.requirements)
        if level and self.difficulty and level != self.difficulty:
            raise ValueError('出题要求与指定难度不一致')
        self.difficulty = self.difficulty or level
        return self
