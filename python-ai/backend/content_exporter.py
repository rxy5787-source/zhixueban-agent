import hashlib
import json

def result_bundle(service_id, job, accepted, rejected, files):
    request=job['request']; points=request['points']; items=[]
    for q in accepted:
        ident=hashlib.sha256(json.dumps([q['question'],q['options'],q['answer'],q['knowledgePoint']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        meta={k:q[k] for k in ['sourceFile','sourceFileId','sourceHash','sourceLocation','evidenceQuote','reviewStatus','reviewModel','generationModel','visualAssisted']}
        meta['questionId']=ident
        meta.update({k:q[k] for k in ('extraction','ocrConfidence','textOnly','reviewMethod','explanationModel','questionConstruction') if k in q})
        items.append({'kind':'question','prompt':q['question'],'options':[q['options'][x] for x in 'ABCD'],'answer':q['answer'],'explanation':q['explanation'],'difficulty':{'简单':1,'中等':2,'困难':3}[q['difficulty']],'points':[q['knowledgePoint']],'ai':meta})
    return {'format':'zhixue-ai-result','version':1,'serviceId':service_id,'jobId':job['id'],'ownerId':job['owner'],'accepted':len(items),'rejected':rejected,'files':files,'generationRequest':{k:request.get(k) for k in ('requirements','questionCount','difficulty')},'reviewNote':'仅依据提取文字出题，自动初筛不代表事实正确率。OCR文字可能有误，请查看识别结果并对照原页；依赖图片、图表或缺失答案的题目不自动入库。','content':{'format':'zhixue-content','version':1,'libraries':[{'name':request['libraryName'],'subject':request['subject'],'kind':'question','points':[dict(p,example='',mnemonic='') for p in points],'items':items}]}}
