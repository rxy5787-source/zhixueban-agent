import re
from pydantic import BaseModel, Field, ConfigDict, field_validator

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
