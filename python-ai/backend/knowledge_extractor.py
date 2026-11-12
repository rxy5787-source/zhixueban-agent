"""Derive a knowledge catalog from real material; never invent fallback summaries."""
import json
import re
import requests
from . import config
from .schemas import Point
from .model_status import checked_model_response

def checked_points(data,material,segments=None):
    points=[];seen=set()
    if not isinstance(data,dict) or not isinstance(data.get('points'),list):raise ValueError('模型没有返回知识点目录')
    for raw in data['points'][:4]:
        if segments is not None:
            if not isinstance(raw,dict):continue
            index=raw.get('sourceIndex')
            if type(index) is not int or not 0<=index<len(segments):continue
            raw={'name':raw.get('name'),'summary':segments[index]}
        try:point=Point.model_validate(raw)
        except ValueError:continue
        if len(re.sub(r'\W','',point.summary))<8 or point.summary not in material or point.name in seen:continue
        seen.add(point.name);points.append(point.model_dump())
    if not points:raise ValueError('无法从资料定位有效知识点摘要，请补充清晰文字资料，或选择已有知识点')
    return points

def derive_points(material,requirements,audit):
    segments=[line.strip() for line in material.splitlines() if len(re.sub(r'\W','',line))>=8]
    if not segments:raise ValueError('资料中没有可引用的完整文字段落')
    text={'type':'string','minLength':1}
    item={'type':'object','properties':{'name':text,'sourceIndex':{'type':'integer','enum':list(range(len(segments)))}},'required':['name','sourceIndex'],'additionalProperties':False}
    schema={'type':'object','properties':{'points':{'type':'array','minItems':1,'maxItems':3,'items':item}},'required':['points'],'additionalProperties':False}
    prompt='从编号资料中识别 1–3 个可考查知识点，优先学习者要求中的重点。name 是简短概念名称，sourceIndex 是支持该知识点的资料编号。不要写摘要，也不要新增资料中没有的概念。只返回 JSON。\n学习者要求：'+requirements+'\n编号资料：\n'+json.dumps([{'sourceIndex':i,'text':text} for i,text in enumerate(segments)],ensure_ascii=False)
    response=requests.post(config.OLLAMA_URL,json={'model':config.TEXT_MODEL,'messages':[{'role':'user','content':prompt}],'stream':False,'think':False,'format':schema,'options':{'temperature':0.2,'num_ctx':4096,'num_predict':1000}},timeout=(10,config.MODEL_TIMEOUT))
    checked_model_response(response,config.TEXT_MODEL);data=response.json();audit('knowledge_points',data)
    return checked_points(json.loads(data['message']['content']),material,segments)
