package com.example.adaptive_quiz_app.learning;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.HashSet;
import java.util.Set;
/** Content and learner evidence are separate. Deletes archive content; history survives. */
public final class LearningStore extends SQLiteOpenHelper  {
    public LearningStore(Context c)  {
        super(c, "zhixue_learning.db", null, 4);
    }
    @Override public void onConfigure(SQLiteDatabase db)  {
        db.setForeignKeyConstraintsEnabled(true);
    }
    @Override public void onCreate(SQLiteDatabase db)  {
        db.execSQL("CREATE TABLE library(id INTEGER PRIMARY KEY,name TEXT NOT NULL,subject TEXT NOT NULL,kind TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0)");
        db.execSQL("CREATE TABLE point(id INTEGER PRIMARY KEY,library_id INTEGER NOT NULL REFERENCES library(id),name TEXT NOT NULL,summary TEXT NOT NULL,example TEXT NOT NULL,mnemonic TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0)");
        db.execSQL("CREATE TABLE item(id INTEGER PRIMARY KEY,library_id INTEGER NOT NULL REFERENCES library(id),kind TEXT NOT NULL,prompt TEXT NOT NULL,options TEXT NOT NULL,answer TEXT NOT NULL,explanation TEXT NOT NULL,difficulty INTEGER NOT NULL,meaning TEXT NOT NULL,example TEXT NOT NULL,context_prompt TEXT NOT NULL,starred INTEGER NOT NULL DEFAULT 0,archived INTEGER NOT NULL DEFAULT 0)");
        db.execSQL("CREATE TABLE item_point(item_id INTEGER NOT NULL REFERENCES item(id),point_id INTEGER NOT NULL REFERENCES point(id),PRIMARY KEY(item_id,point_id))");
        db.execSQL("CREATE TABLE state(owner_id INTEGER NOT NULL,skill TEXT NOT NULL,mastery REAL NOT NULL,seen INTEGER NOT NULL,last_at INTEGER NOT NULL,due_at INTEGER NOT NULL,interval_days INTEGER NOT NULL,PRIMARY KEY(owner_id,skill))");
        db.execSQL("CREATE TABLE session(id INTEGER PRIMARY KEY,library_id INTEGER NOT NULL REFERENCES library(id),mode TEXT NOT NULL,plan TEXT NOT NULL,position INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,finished INTEGER NOT NULL DEFAULT 0)");
        db.execSQL("CREATE TABLE attempt(id INTEGER PRIMARY KEY,session_id INTEGER NOT NULL REFERENCES session(id),position INTEGER NOT NULL,item_id INTEGER NOT NULL REFERENCES item(id),prompt TEXT NOT NULL,expected TEXT NOT NULL,response TEXT NOT NULL,correct INTEGER NOT NULL,confidence INTEGER NOT NULL,skill TEXT NOT NULL,elapsed_ms INTEGER NOT NULL,at INTEGER NOT NULL,UNIQUE(session_id,position))");
        db.execSQL("CREATE TABLE attempt_point(attempt_id INTEGER NOT NULL REFERENCES attempt(id),point_id INTEGER NOT NULL REFERENCES point(id),PRIMARY KEY(attempt_id,point_id))");
        db.execSQL("CREATE TABLE self_rating(id INTEGER PRIMARY KEY,item_id INTEGER NOT NULL REFERENCES item(id),rating INTEGER NOT NULL,at INTEGER NOT NULL)");
        db.execSQL("CREATE TABLE reference(id INTEGER PRIMARY KEY,library_id INTEGER NOT NULL REFERENCES library(id),point_id INTEGER REFERENCES point(id),name TEXT NOT NULL,path TEXT NOT NULL,mime TEXT NOT NULL)");
        db.execSQL("CREATE INDEX attempt_at ON attempt(at)");
        db.execSQL("CREATE INDEX item_library ON item(library_id,archived)");
        addVersionTwo(db);
        addVersionThree(db);
        addVersionFour(db);
    }
    private void addVersionTwo(SQLiteDatabase db)  {
        db.execSQL("ALTER TABLE session ADD COLUMN strategy TEXT NOT NULL DEFAULT 'adaptive'");
        db.execSQL("ALTER TABLE session ADD COLUMN target_point INTEGER NOT NULL DEFAULT 0");
        db.execSQL("CREATE TABLE state_change(id INTEGER PRIMARY KEY,attempt_id INTEGER NOT NULL REFERENCES attempt(id),owner_id INTEGER NOT NULL,skill TEXT NOT NULL,before_value REAL NOT NULL,after_value REAL NOT NULL,at INTEGER NOT NULL)");
        db.execSQL("CREATE TABLE task(id INTEGER PRIMARY KEY,source_session INTEGER NOT NULL REFERENCES session(id),library_id INTEGER NOT NULL REFERENCES library(id),point_id INTEGER NOT NULL DEFAULT 0,stage TEXT NOT NULL,due_at INTEGER NOT NULL,completed INTEGER NOT NULL DEFAULT 0,practice_session INTEGER REFERENCES session(id),UNIQUE(source_session,stage))");
    }
    private void addVersionThree(SQLiteDatabase db) {
        // Keep historical rows and estimates unchanged. Old updates did not record these inputs.
        db.execSQL("ALTER TABLE state_change ADD COLUMN guess REAL");
        db.execSQL("ALTER TABLE state_change ADD COLUMN slip REAL");
        db.execSQL("ALTER TABLE state_change ADD COLUMN learn REAL");
        db.execSQL("ALTER TABLE state_change ADD COLUMN posterior REAL");
        db.execSQL("ALTER TABLE state_change ADD COLUMN model_version TEXT NOT NULL DEFAULT 'legacy-no-trace'");
    }
    @Override public void onUpgrade(SQLiteDatabase db,int old,int next)  {
        if(old<2)addVersionTwo(db);
        if(old<3)addVersionThree(db);
        if(old<4)addVersionFour(db);
    }
    private void addVersionFour(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE ai_source(id INTEGER PRIMARY KEY,item_id INTEGER NOT NULL REFERENCES item(id),service_id TEXT NOT NULL,question_id TEXT NOT NULL,job_id TEXT NOT NULL,metadata TEXT NOT NULL,UNIQUE(service_id,question_id,item_id))");
    }
    public synchronized JSONArray rows(String sql, String... args)  {
        JSONArray out = new JSONArray();
        try (Cursor c = getReadableDatabase().rawQuery(sql,args))  {
            while(c.moveToNext())  {
                JSONObject r = new JSONObject();
                for(int i=0;i<c.getColumnCount();i++)  {
                    try  {
                        switch(c.getType(i))  {
                            case Cursor.FIELD_TYPE_NULL: r.put(c.getColumnName(i),JSONObject.NULL);
                            break;
                            case Cursor.FIELD_TYPE_INTEGER: r.put(c.getColumnName(i),c.getLong(i));
                            break;
                            case Cursor.FIELD_TYPE_FLOAT: r.put(c.getColumnName(i),c.getDouble(i));
                            break;
                            default: r.put(c.getColumnName(i),c.getString(i));
                        }
                    }
                    catch(JSONException e)  {
                        throw new IllegalStateException(e);
                    }
                }
                out.put(r);
            }
        }
        return out;
    }
    public JSONObject one(String sql,String... args)  {
        return rows(sql,args).optJSONObject(0);
    }
    public long count(String sql,String... args)  {
        JSONObject o=one(sql,args);
        return o==null?0:o.optLong("n");
    }
    public synchronized long insert(String table, JSONObject row)  {
        ContentValues v = values(row);
        return getWritableDatabase().insertOrThrow(table,null,v);
    }
    private ContentValues values(JSONObject row)  {
        ContentValues v=new ContentValues();
        java.util.Iterator<String> keys=row.keys();
        while(keys.hasNext())  {
            String key=keys.next();
            Object val=row.opt(key);
            if(val==JSONObject.NULL) v.putNull(key);
            else if(val instanceof Number)  {
                if(val instanceof Double||val instanceof Float) v.put(key,((Number)val).doubleValue());
                else v.put(key,((Number)val).longValue());
            }
            else v.put(key,String.valueOf(val));
        }
        return v;
    }
    public synchronized void edit(String table,long id,JSONObject row)  {
        getWritableDatabase().update(table,values(row),"id=?",new String[] {
            ""+id
        }
        );
    }
    public static JSONObject obj(Object... pairs)  {
        JSONObject o=new JSONObject();
        try  {
            for(int i=0;i<pairs.length;i+=2) o.put((String)pairs[i],pairs[i+1]);
        }
        catch(JSONException e)  {
            throw new IllegalArgumentException(e);
        }
        return o;
    }
    public synchronized void seed() throws JSONException  {
        if(count("SELECT COUNT(*) n FROM library")>0) return;
        importContent(sample());
        importContent(SubjectSamples.content());
    }
    public static JSONObject sample() throws JSONException  {
        JSONArray libs=new JSONArray();
        JSONArray points=new JSONArray();
        points.put(obj("name","筛选与排序","summary","WHERE 筛选行，ORDER BY 排序；ASC 升序，DESC 降序。","example","SELECT name FROM students WHERE score >= 60 ORDER BY score DESC;","mnemonic","先筛选，再排序（记忆方法）"));
        points.put(obj("name","聚合与分组","summary","COUNT、SUM、AVG 对数据聚合；GROUP BY 分组，HAVING 筛选聚合后的分组。","example","SELECT class, AVG(score) FROM students GROUP BY class HAVING AVG(score) >= 60;","mnemonic","WHERE 管行，HAVING 管组（记忆方法）"));
        points.put(obj("name","连接与空值","summary","INNER JOIN 返回匹配行；LEFT JOIN 保留左表全部行。NULL 使用 IS NULL 判断。","example","SELECT s.name FROM students s LEFT JOIN grades g ON s.id=g.student_id WHERE g.student_id IS NULL;","mnemonic","空值不是零，也不是空字符串。"));
        points.put(obj("name","键与约束","summary","主键唯一且非空，外键用于维护表间引用完整性。","example","CREATE TABLE grades(student_id INTEGER REFERENCES students(id), score INTEGER);","mnemonic","主键标识，外键关联（记忆方法）"));
        JSONArray questions=new JSONArray();
        String[][] data= {
            {
                "筛选与排序","筛选成绩大于等于 60 的学生，应使用哪个子句？","WHERE|ORDER BY|GROUP BY|LIMIT","A","WHERE 在聚合前筛选行。"
            }
            ,              {
                "筛选与排序","按分数从高到低排序，应使用？","ORDER BY score ASC|ORDER BY score DESC|GROUP BY score|WHERE score DESC","B","DESC 是降序；ASC 是升序。"
            }
            ,              {
                "筛选与排序","只取排序后的前三行，SQLite 中使用？","TOP 3|GROUP BY 3|LIMIT 3|HAVING 3","C","SQLite 使用 LIMIT 限制返回行数。"
            }
            ,              {
                "筛选与排序","匹配以 Li 开头的姓名，应使用？","name LIKE '%Li'|name = 'Li%'|name LIKE 'Li%'|name IS 'Li%'","C","% 匹配零个或多个字符。Li% 表示以 Li 开头。"
            }
            ,              {
                "聚合与分组","统计表的总行数，应使用？","SUM(*)|COUNT(*)|AVG(*)|MAX(*)","B","COUNT(*) 统计所有行，包括含 NULL 的行。"
            }
            ,              {
                "聚合与分组","按班级统计平均分，需要哪个子句？","ORDER BY class|WHERE class|GROUP BY class|LIMIT class","C","GROUP BY class 将同班记录分组后聚合。"
            }
            ,              {
                "聚合与分组","筛选平均分超过 80 的班级，应使用？","WHERE AVG(score)>80|HAVING AVG(score)>80|LIMIT AVG(score)>80|ORDER BY AVG(score)>80","B","HAVING 筛选聚合后的分组。"
            }
            ,              {
                "聚合与分组","COUNT(score) 如何处理 score 为 NULL 的行？","计入|忽略|报错|变成 0","B","COUNT(列) 忽略该列中的 NULL，COUNT(*) 不忽略行。"
            }
            ,              {
                "连接与空值","保留学生表所有学生，即使没有成绩，应使用？","INNER JOIN|LEFT JOIN|CROSS JOIN|仅 WHERE","B","LEFT JOIN 保留左表全部行，右表未匹配列为 NULL。"
            }
            ,              {
                "连接与空值","判断 email 为空值的正确表达式是？","email = NULL|email == NULL|email IS NULL|email = ''","C","SQL 中 NULL 判断使用 IS NULL。"
            }
            ,              {
                "连接与空值","INNER JOIN 返回什么？","左表全部行|右表全部行|满足连接条件的匹配行|所有组合","C","INNER JOIN 只保留满足连接条件的匹配记录。"
            }
            ,              {
                "连接与空值","两个表不加条件做 CROSS JOIN，分别有 3 行和 4 行，结果多少行？","3|4|7|12","D","笛卡尔积产生 3×4=12 行。"
            }
            ,              {
                "键与约束","关系模型中的主键应该满足？","唯一且非空|可重复|只能是字符串|必须为外键","A","主键用于唯一标识记录，不允许空值。"
            }
            ,              {
                "键与约束","外键的主要作用是？","自动排序|维护引用完整性|自动加密|替代所有索引","B","外键将子表引用约束到父表的有效键。"
            }
            ,              {
                "键与约束","删除表中符合条件的行使用？","DROP TABLE|DELETE FROM ... WHERE ...|ALTER TABLE|CREATE TABLE","B","DELETE 删除数据行，DROP TABLE 删除整个表。"
            }
            ,              {
                "键与约束","修改已有行的 score 值使用？","INSERT|SELECT|UPDATE|CREATE","C","UPDATE 修改已有记录，WHERE 可限定目标行。"
            }
        }
        ;
        for(int i=0;i<data.length;i++)  {
            String[] d=data[i];
            questions.put(obj("kind","question","prompt",d[1],"options",new JSONArray(java.util.Arrays.asList(d[2].split("\\|"))),"answer",d[3],"explanation",d[4],"difficulty",1+i%3,"points",new JSONArray().put(d[0])));
        }
        libs.put(obj("name","SQL 基础知识","subject","计算机","kind","question","points",points,"items",questions));
        String[][] words= {
            {
                "abandon","放弃；抛弃","Never abandon your dreams.","Never ____ your dreams."
            }
            ,              {
                "achieve","实现；达到","You can achieve your goal.","You can ____ your goal."
            }
            ,              {
                "benefit","益处；使受益","Reading will benefit you.","Reading will ____ you."
            }
            ,              {
                "confident","自信的","She feels confident today.","She feels ____ today."
            }
            ,              {
                "develop","发展；开发","We develop new skills.","We ____ new skills."
            }
            ,              {
                "efficient","高效的","This is an efficient method.","This is an ____ method."
            }
            ,              {
                "focus","集中注意力","Please focus on the task.","Please ____ on the task."
            }
            ,              {
                "improve","改进；提高","Practice helps improve memory.","Practice helps ____ memory."
            }
            ,              {
                "knowledge","知识","Knowledge grows with practice.","____ grows with practice."
            }
            ,              {
                "memory","记忆","Sleep supports memory.","Sleep supports ____."
            }
            ,              {
                "review","复习；回顾","We review our lessons.","We ____ our lessons."
            }
            ,              {
                "strategy","策略","Choose a useful strategy.","Choose a useful ____."
            }
        }
        ;
        JSONArray vocab=new JSONArray();
        for(String[] w:words) vocab.put(obj("kind","word","prompt",w[0],"meaning",w[1],"example",w[2],"context_prompt",w[3],"difficulty",1,"points",new JSONArray()));
        libs.put(obj("name","英语 · 核心词汇","subject","英语","kind","word","points",new JSONArray(),"items",vocab));
        return obj("format","zhixue-content","version",1,"libraries",libs);
    }
    private static String required(JSONObject o,String key) throws JSONException  {
        String s=o.getString(key).trim();
        if(s.isEmpty()) throw new JSONException("字段不能为空："+key);
        return s;
    }
    public static void validateItem(JSONObject item,String kind,Set<String> points) throws JSONException  {
        required(item,"prompt");
        if(!kind.equals(item.getString("kind"))) throw new JSONException("知识库内类型不一致");
        int d=item.getInt("difficulty");
        if(d<1||d>3) throw new JSONException("difficulty 必须为 1–3");
        JSONArray links=item.getJSONArray("points");
        for(int i=0;i<links.length();i++) if(!points.contains(links.getString(i))) throw new JSONException("知识点不存在："+links.getString(i));
        if(kind.equals("question"))  {
            JSONArray opts=item.getJSONArray("options");
            if(opts.length()!=4) throw new JSONException("单选题需要 4 个选项");
            for(int i=0;i<4;i++) if(opts.getString(i).trim().isEmpty()) throw new JSONException("选项不能为空");
            if(!required(item,"answer").matches("[ABCD]")) throw new JSONException("答案必须为 A/B/C/D");
            required(item,"explanation");
            if(links.length()==0) throw new JSONException("题目至少关联一个知识点");
        }
        else  {
            required(item,"meaning");
            required(item,"example");
            String context=required(item,"context_prompt");
            if(!context.contains("____")) throw new JSONException("语境题必须包含 ____ 空位");
            if(context.toLowerCase(java.util.Locale.ROOT).contains(item.getString("prompt").toLowerCase(java.util.Locale.ROOT))) throw new JSONException("语境题不能泄露拼写答案");
        }
    }
    public synchronized String importContent(JSONObject root) throws JSONException  {
        if(!"zhixue-content".equals(root.getString("format"))||root.getInt("version")!=1) throw new JSONException("不支持的内容格式或版本");
        JSONArray libs=root.getJSONArray("libraries");
        for(int n=0;n<libs.length();n++)  {
            JSONObject l=libs.getJSONObject(n);
            required(l,"name");
            required(l,"subject");
            String kind=l.getString("kind");
            if(!kind.equals("word")&&!kind.equals("question")) throw new JSONException("kind 必须为 word 或 question");
            Set<String> names=new HashSet<>();
            JSONArray ps=l.getJSONArray("points");
            for(int i=0;i<ps.length();i++)  {
                JSONObject p=ps.getJSONObject(i);
                if(!names.add(required(p,"name"))) throw new JSONException("重复知识点");
                required(p,"summary");
            }
            JSONArray items=l.getJSONArray("items");
            for(int i=0;i<items.length();i++)  {
                try  {
                    validateItem(items.getJSONObject(i),kind,names);
                }
                catch(JSONException e)  {
                    throw new JSONException(l.getString("name")+" 第 "+(i+1)+" 条："+e.getMessage());
                }
            }
        }
        int added=0, skipped=0;
        SQLiteDatabase db=getWritableDatabase();
        db.beginTransaction();
        try  {
            for(int n=0;n<libs.length();n++)  {
                JSONObject l=libs.getJSONObject(n);
                JSONObject existing=one("SELECT * FROM library WHERE name=? AND subject=? AND kind=? AND archived=0",l.getString("name"),l.getString("subject"),l.getString("kind"));
                long lid=existing==null?insert("library",obj("name",l.getString("name"),"subject",l.getString("subject"),"kind",l.getString("kind"))):existing.optLong("id");
                JSONArray ps=l.getJSONArray("points");
                for(int i=0;i<ps.length();i++)  {
                    JSONObject p=ps.getJSONObject(i);
                    if(one("SELECT id FROM point WHERE library_id=? AND name=? AND archived=0",""+lid,p.getString("name"))==null) insert("point",obj("library_id",lid,"name",p.getString("name"),"summary",p.getString("summary"),"example",p.optString("example"),"mnemonic",p.optString("mnemonic")));
                }
                JSONArray items=l.getJSONArray("items");
                for(int i=0;i<items.length();i++)  {
                    JSONObject x=items.getJSONObject(i);
                    if(one("SELECT id FROM item WHERE library_id=? AND prompt=? AND kind=? AND archived=0",""+lid,x.getString("prompt"),x.getString("kind"))!=null)  {
                        skipped++;
                        continue;
                    }
                    long id=insert("item",obj("library_id",lid,"kind",x.getString("kind"),"prompt",x.getString("prompt"),"options",x.optJSONArray("options")==null?"[]":x.getJSONArray("options").toString(),"answer",x.optString("answer",x.getString("prompt")),"explanation",x.optString("explanation"),"difficulty",x.getInt("difficulty"),"meaning",x.optString("meaning"),"example",x.optString("example"),"context_prompt",x.optString("context_prompt")));
                    JSONArray links=x.getJSONArray("points");
                    for(int j=0;j<links.length();j++)  {
                        JSONObject p=one("SELECT id FROM point WHERE library_id=? AND name=? AND archived=0",""+lid,links.getString(j));
                        insert("item_point",obj("item_id",id,"point_id",p.getLong("id")));
                    }
                    added++;
                }
            }
            db.setTransactionSuccessful();
        }
        finally  {
            db.endTransaction();
        }
        return "新增 "+added+" 条内容，跳过 "+skipped+" 条同名重复内容（保留原记录）";
    }
    /** Validated AI content and provenance share one transaction; learner evidence is untouched. */
    public synchronized String importAiResult(JSONObject result,String owner) throws JSONException {
        if(!"zhixue-ai-result".equals(result.getString("format"))||result.getInt("version")!=1||!owner.equals(result.getString("ownerId")))throw new JSONException("AI 结果不属于当前账号或版本不支持");
        String service=required(result,"serviceId"),job=required(result,"jobId");
        JSONObject content=result.getJSONObject("content");JSONArray libraries=content.getJSONArray("libraries");
        int count=0;
        for(int n=0;n<libraries.length();n++) {
            JSONObject l=libraries.getJSONObject(n);if(!"question".equals(l.getString("kind")))throw new JSONException("AI 入口目前仅接收单选题");
            JSONArray items=l.getJSONArray("items");
            for(int i=0;i<items.length();i++) {
                JSONObject meta=items.getJSONObject(i).getJSONObject("ai");
                required(meta,"questionId");required(meta,"sourceFileId");required(meta,"sourceFile");required(meta,"sourceHash");required(meta,"sourceLocation");required(meta,"evidenceQuote");required(meta,"generationModel");required(meta,"reviewModel");
                if(!"auto_prechecked".equals(meta.getString("reviewStatus"))||meta.getBoolean("visualAssisted"))throw new JSONException("未验证视觉题不能导入正式题库");
                count++;
            }
        }
        if(count==0)throw new JSONException("本次没有通过检查的题目");
        SQLiteDatabase sql=getWritableDatabase();sql.beginTransaction();
        try {
            String summary=importContent(content);
            for(int n=0;n<libraries.length();n++) {
                JSONObject l=libraries.getJSONObject(n),library=one("SELECT id FROM library WHERE name=? AND subject=? AND kind='question' AND archived=0",l.getString("name"),l.getString("subject"));
                JSONArray items=l.getJSONArray("items");
                for(int i=0;i<items.length();i++) {
                    JSONObject q=items.getJSONObject(i),meta=q.getJSONObject("ai");
                    JSONObject item=one("SELECT * FROM item WHERE library_id=? AND prompt=? AND kind='question' AND archived=0",""+library.getLong("id"),q.getString("prompt"));
                    if(!item.getString("answer").equals(q.getString("answer"))||!new JSONArray(item.getString("options")).toString().equals(q.getJSONArray("options").toString()))throw new JSONException("已有同题干内容的选项或答案不同，请人工处理冲突");
                    if(!item.optString("explanation").equals(q.optString("explanation"))||item.optInt("difficulty")!=q.optInt("difficulty")||count("SELECT COUNT(*) n FROM item_point WHERE item_id=?",""+item.getLong("id"))!=q.getJSONArray("points").length())throw new JSONException("已有同题干内容的解析、难度或知识点不同，请人工处理冲突");
                    for(int p=0;p<q.getJSONArray("points").length();p++)if(count("SELECT COUNT(*) n FROM item_point ip JOIN point p ON p.id=ip.point_id WHERE ip.item_id=? AND p.name=?",""+item.getLong("id"),q.getJSONArray("points").getString(p))==0)throw new JSONException("已有题目知识点关联不同，请人工处理冲突");
                    if(one("SELECT id FROM ai_source WHERE service_id=? AND question_id=? AND item_id=?",service,meta.getString("questionId"),""+item.getLong("id"))==null)
                        insert("ai_source",obj("item_id",item.getLong("id"),"service_id",service,"question_id",meta.getString("questionId"),"job_id",job,"metadata",meta.toString()));
                }
            }
            sql.setTransactionSuccessful();return summary+"；AI 来源已保存（自动初筛非正确性保证）";
        } finally {sql.endTransaction();}
    }
    /** Read-only generation targets. Missing observations remain explicitly unassessed. */
    public synchronized JSONObject generationPlan(long library) throws JSONException {
        JSONArray selected=new JSONArray(),evidence=new JSONArray();StringBuilder context=new StringBuilder();
        if(one("SELECT id FROM library WHERE id=? AND kind='question' AND archived=0",""+library)==null)return obj("points",selected,"evidence",evidence,"difficulty",1,"requirements","");
        JSONArray targets=rows("SELECT p.id,p.name,p.summary,COALESCE(s.seen,0) seen,s.mastery FROM point p LEFT JOIN state s ON s.owner_id=p.id AND s.skill='knowledge' WHERE p.library_id=? AND p.archived=0 AND TRIM(p.summary)<>'' ORDER BY CASE WHEN COALESCE(s.seen,0)>0 AND s.mastery<0.75 THEN 0 WHEN COALESCE(s.seen,0)=0 THEN 1 ELSE 2 END,s.mastery,p.id LIMIT 3",""+library);
        double total=0;boolean focus=targets.length()>0&&(targets.optJSONObject(0).optInt("seen")==0||targets.optJSONObject(0).optDouble("mastery")<.75);
        for(int i=0;i<targets.length();i++) {
            JSONObject p=targets.getJSONObject(i);int seen=p.optInt("seen");double mastery=seen==0?LearningEngine.INITIAL:p.optDouble("mastery");
            if(focus&&seen>0&&mastery>=.75)continue;
            String summary=p.getString("summary");if(summary.length()>2000)summary=summary.substring(0,2000);
            selected.put(obj("name",p.getString("name"),"summary",summary));
            evidence.put(obj("id",p.getLong("id"),"name",p.getString("name"),"seen",seen,"mastery",seen==0?JSONObject.NULL:mastery));
            context.append(p.getString("name")).append("：").append(seen==0?"待评估（尚无作答证据）":"掌握估计 "+Math.round(mastery*100)+"%，已有 "+seen+" 次证据").append('；');total+=mastery;
        }
        int difficulty=selected.length()==0?1:LearningEngine.targetDifficulty(total/selected.length());
        String instructions=selected.length()==0?"":"基于当前题库学习记录的出题重点（掌握概率为模型估计）："+context+"仅围绕所选知识点，依据本次上传资料生成新的单选题；优先巩固薄弱点并评估未测试点。资料不支持的内容不要编造。";
        return obj("points",selected,"evidence",evidence,"difficulty",difficulty,"requirements",instructions);
    }
    /** A tapped card uses the same audited submission path as adaptive practice. */
    public synchronized long startQuestion(long library,long item) throws JSONException {
        if(one("SELECT i.id FROM item i JOIN library l ON l.id=i.library_id WHERE i.id=? AND i.library_id=? AND i.kind='question' AND i.archived=0 AND l.archived=0",""+item,""+library)==null)throw new JSONException("题目不属于当前题库或已归档");
        return insert("session",obj("library_id",library,"mode","question","plan",new JSONArray().put(item).toString(),"created_at",System.currentTimeMillis(),"strategy","card","target_point",0));
    }
    public JSONObject state(long id,String skill)  {
        JSONObject s=one("SELECT * FROM state WHERE owner_id=? AND skill=?",""+id,skill);
        return s==null?obj("mastery",LearningEngine.INITIAL,"seen",0,"last_at",0,"due_at",0,"interval_days",0):s;
    }
    public double mastery(long item,String mode)  {
        if(!mode.equals("question")) return state(item,mode).optDouble("mastery");
        JSONArray ps=rows("SELECT point_id FROM item_point WHERE item_id=?",""+item);
        double total=0;
        for(int i=0;i<ps.length();i++) total+=state(ps.optJSONObject(i).optLong("point_id"),"knowledge").optDouble("mastery");
        return ps.length()==0?LearningEngine.INITIAL:total/ps.length();
    }
    public synchronized long start(long library,String mode,int size,String filter,long point) throws JSONException  {
        long now=System.currentTimeMillis();
        List<JSONObject> candidates=candidates(library,mode,filter,point,now);
        List<JSONObject> chosen=new ArrayList<>();
        if("random".equals(filter)) {
            chosen.addAll(candidates);
            Collections.shuffle(chosen);
        } else if("diagnostic".equals(filter)) {
            // Greedy breadth first: cover new points before adding another question on the same point.
            Set<Long> covered=new HashSet<>();
            while(!candidates.isEmpty()&&chosen.size()<size) {
                int best=0,bestNew=-1;
                boolean hasNotRecent=false;
                for(JSONObject x:candidates)if(x.optInt("recent")==0){hasNotRecent=true;break;}
                boolean bestFresh=false;
                for(int i=0;i<candidates.size();i++) {
                    JSONObject x=candidates.get(i);
                    if(hasNotRecent&&x.optInt("recent")>0)continue;
                    int newlyCovered=0;
                    JSONArray points=rows("SELECT point_id FROM item_point WHERE item_id=?",""+x.optLong("id"));
                    for(int j=0;j<points.length();j++)if(!covered.contains(points.optJSONObject(j).optLong("point_id")))newlyCovered++;
                    boolean fresh=x.optInt("seen")==0;
                    if(newlyCovered>bestNew||(newlyCovered==bestNew&&fresh&&!bestFresh)) {
                        best=i;bestNew=newlyCovered;bestFresh=fresh;
                    }
                }
                JSONObject x=candidates.remove(best);chosen.add(x);
                JSONArray links=rows("SELECT point_id FROM item_point WHERE item_id=?",""+x.optLong("id"));
                for(int j=0;j<links.length();j++)covered.add(links.optJSONObject(j).optLong("point_id"));
            }
        } else {
            // Do not repeat a recently answered item while a non-recent eligible alternative exists.
            List<JSONObject> notRecent=new ArrayList<>(),recent=new ArrayList<>();
            for(JSONObject x:candidates)(x.optInt("recent")==0?notRecent:recent).add(x);
            chooseBalanced(notRecent,size,chosen);
            chooseBalanced(recent,size,chosen);
        }
        JSONArray plan=new JSONArray();
        for(int i=0;i<Math.min(size,chosen.size());i++)plan.put(chosen.get(i).getLong("id"));
        if(plan.length()==0)return 0;
        return insert("session",obj("library_id",library,"mode",mode,"plan",plan.toString(),"created_at",now,"strategy",filter,"target_point",point));
    }
    private List<JSONObject> candidates(long library,String mode,String filter,long point,long now) throws JSONException {
        JSONArray items=rows("SELECT * FROM item WHERE library_id=? AND archived=0 ORDER BY id",""+library);
        List<JSONObject> candidates=new ArrayList<>();
        for(int i=0;i<items.length();i++)  {
            JSONObject x=items.getJSONObject(i);
            long id=x.getLong("id");
            if(point>0&&count("SELECT COUNT(*) n FROM item_point WHERE item_id=? AND point_id=?",""+id,""+point)==0) continue;
            if("basic".equals(filter)&&x.optInt("difficulty")!=1)continue;
            if("application".equals(filter)&&x.optInt("difficulty")<2)continue;
            if("star".equals(filter)&&x.optInt("starred")==0) continue;
            if("wrong".equals(filter)&&count("SELECT COUNT(*) n FROM attempt WHERE item_id=? AND correct=0",""+id)==0) continue;
            if("verify".equals(filter)&&count("SELECT COUNT(*) n FROM attempt WHERE item_id=? AND correct=1 AND confidence<2",""+id)==0) continue;
            JSONObject history=one("SELECT COUNT(*) seen,MAX(at) last_at FROM attempt WHERE item_id=? AND skill=?",""+id,mode);
            x.put("seen",history.optInt("seen"));
            x.put("recent",count("SELECT COUNT(*) n FROM attempt WHERE item_id=? AND skill=? AND at>?",""+id,mode,""+(now-86400000L)));
            x.put("priority",priority(x,mode,now));
            candidates.add(x);
        }
        java.util.Comparator<JSONObject> cmp=(a,b)->Double.compare(b.optDouble("priority"),a.optDouble("priority"));
        candidates.sort(cmp);
        return candidates;
    }
    private void chooseBalanced(List<JSONObject> candidates,int size,List<JSONObject> chosen) {
        List<JSONObject> old=new ArrayList<>(),fresh=new ArrayList<>();
        for(JSONObject x:candidates)(x.optInt("seen")==0?fresh:old).add(x);
        int slots=size-chosen.size(),newQuota=old.isEmpty()?slots:Math.max(1,slots/3);
        int oi=0,ni=0;
        while(chosen.size()<size&&(oi<old.size()||ni<fresh.size())) {
            if(ni<fresh.size()&&(ni<newQuota||oi>=old.size()))chosen.add(fresh.get(ni++));
            else if(oi<old.size())chosen.add(old.get(oi++));
            else break;
        }
    }
    private double priority(JSONObject item,String mode,long now) {
        long id=item.optLong("id");
        JSONObject history=one("SELECT MAX(at) last_at FROM attempt WHERE item_id=? AND skill=?",""+id,mode);
        JSONObject s=state(id,mode);
        if("question".equals(mode)) {
            s=one("SELECT MIN(s.due_at) due_at FROM state s JOIN item_point ip ON ip.point_id=s.owner_id WHERE s.skill='knowledge' AND ip.item_id=?",""+id);
        }
        int recent=(int)count("SELECT COUNT(*) n FROM attempt WHERE item_id=? AND skill=? AND at>?",""+id,mode,""+(now-86400000L));
        return LearningEngine.priority(mastery(id,mode),s==null?0:s.optLong("due_at"),history.optLong("last_at"),item.optInt("difficulty"),recent,now);
    }
    /** Current, database-backed explanation; never substitutes accuracy for a BKT state. */
    public synchronized JSONObject recommendation(long itemId,String mode,String strategy) throws JSONException {
        JSONObject item=one("SELECT * FROM item WHERE id=?",""+itemId);
        if(item==null)throw new JSONException("内容不存在");
        long now=System.currentTimeMillis();
        JSONArray points=new JSONArray();
        int seen=Integer.MAX_VALUE;
        StringBuilder names=new StringBuilder();
        String recentQuery;
        long due=0;
        if("question".equals(mode)) {
            JSONArray linked=rows("SELECT p.id,p.name FROM point p JOIN item_point ip ON ip.point_id=p.id WHERE ip.item_id=? ORDER BY p.id",""+itemId);
            for(int i=0;i<linked.length();i++) {
                JSONObject point=linked.getJSONObject(i),state=state(point.getLong("id"),"knowledge");
                int observations=state.optInt("seen");seen=Math.min(seen,observations);
                if(i>0)names.append("、");names.append(point.optString("name"));
                points.put(obj("id",point.optLong("id"),"name",point.optString("name"),"seen",observations,"mastery",state.optDouble("mastery")));
                if(state.optLong("due_at")>0&&(due==0||state.optLong("due_at")<due))due=state.optLong("due_at");
            }
            JSONObject deadline=one("SELECT MIN(s.due_at) due_at FROM state s JOIN item_point ip ON ip.point_id=s.owner_id WHERE s.skill='knowledge' AND ip.item_id=?",""+itemId);
            due=deadline==null?0:deadline.optLong("due_at");
            recentQuery="SELECT a.correct FROM attempt a WHERE a.id IN (SELECT ap.attempt_id FROM attempt_point ap WHERE ap.point_id IN (SELECT point_id FROM item_point WHERE item_id=?)) ORDER BY a.at DESC,a.id DESC LIMIT 5";
        } else {
            JSONObject state=state(itemId,mode);seen=state.optInt("seen");due=state.optLong("due_at");
            String capability="recognition".equals(mode)?"词义辨认":"recall".equals(mode)?"拼写回忆":"语境运用";
            names.append(item.optString("prompt")).append(" · ").append(capability);
            points.put(obj("id",itemId,"name",names.toString(),"seen",seen,"mastery",state.optDouble("mastery")));
            recentQuery="SELECT correct FROM attempt WHERE item_id=? AND skill='"+mode.replace("'","''")+"' ORDER BY at DESC,id DESC LIMIT 5";
        }
        if(seen==Integer.MAX_VALUE)seen=0;
        JSONArray recentEvidence=rows(recentQuery,""+itemId);
        int recentCorrect=0;
        for(int i=0;i<recentEvidence.length();i++)recentCorrect+=recentEvidence.optJSONObject(i).optInt("correct");
        double mastery=mastery(itemId,mode);
        JSONObject history=one("SELECT MAX(at) last_at FROM attempt WHERE item_id=? AND skill=?",""+itemId,mode);
        int recent=(int)count("SELECT COUNT(*) n FROM attempt WHERE item_id=? AND skill=? AND at>?",""+itemId,mode,""+(now-86400000L));
        LearningEngine.PriorityTrace factors=LearningEngine.priorityTrace(mastery,due,history.optLong("last_at"),item.optInt("difficulty"),recent,now);
        int target=LearningEngine.targetDifficulty(mastery);
        String reason,goal;
        if("random".equals(strategy)) {
            reason="本轮为随机对照，题目随机抽取，不依据掌握概率排序。";
            goal="作为随机练习，积累独立答题证据。";
        } else if("diagnostic".equals(strategy)) {
            reason="本轮为初始测试，优先覆盖不同知识点与未答题目；小样本结果仍需后续验证。";
            goal="收集初始作答证据，建立各知识点的模型估计。";
        } else if(seen==0) {
            reason="相关能力尚未全部评估，使用初始先验参与排序，先补充测试证据。";
            goal="完成本题，建立待评估知识点的初始证据。";
        } else if(due>0&&due<=now) {
            reason="相关知识点已到复习时间，结合薄弱程度与题目难度优先安排。";
            goal=mastery<.6?"复查薄弱点，巩固基础并减少猜测。":"检验间隔后的保持情况。";
        } else if(mastery<.6) {
            reason="当前模型估计偏低，优先巩固，并匹配较适合的难度。";
            goal="查清错误原因，再次验证基础理解。";
        } else {
            reason="已有一定掌握证据，按当前估计匹配目标难度 "+target+"/3 的题目。";
            goal=target==3?"尝试较高难度，检验迁移与应用能力。":"通过适当难度继续验证理解。";
        }
        if("basic".equals(strategy))reason="本轮限定基础题（难度1/3）。"+reason;
        else if("application".equals(strategy))reason="本轮限定应用题（难度至少2/3）。"+reason;
        else if("wrong".equals(strategy))reason="该题有历史答错记录，属于错题练习范围。"+reason;
        else if("verify".equals(strategy))reason="该题曾答对但把握不足，本轮用于再次验证。"+reason;
        else if("star".equals(strategy))reason="该题已收藏，属于收藏练习范围。"+reason;
        else if("delayed".equals(strategy))reason="本轮属于间隔后的延迟复测。"+reason;
        else if("card".equals(strategy)){reason="你在题库中主动选择了这张题目卡片。";goal="完成作答后更新关联知识点的掌握估计，供下一轮自适应选题或生成使用。";}
        if(recent>0&&!"random".equals(strategy))reason+="截至现在，该题24小时内做过 "+recent+" 次；非近期题优先，符合条件的替代题不足时允许回退，本轮不重复填充同题。";
        String probability=seen==0?"待评估（内部先验参与排序，不展示为测得概率）":Math.round(mastery*100)+"%（BKT模型估计，参数未经校准）";
        String performance=recentEvidence.length()==0?"暂无相关作答":"最近 "+recentEvidence.length()+" 次相关作答答对 "+recentCorrect+" 次";
        String summary="对应知识点："+(names.length()==0?"尚未关联知识点":names)+"\n最近表现："+performance+"\n当前估计掌握概率："+probability+
                "\n本题难度："+item.optInt("difficulty")+"/3；目标难度："+target+"/3（综合排序因素之一）"+
                "\n推荐原因："+reason+"\n本次目标："+goal;
        JSONObject scores=obj("weakness",factors.weakness,"overdue",factors.overdue,"spacing",factors.spacing,"difficultyFit",factors.difficultyFit,"repetition",factors.repetition,"total",factors.total);
        return obj("summary",summary,"points",points,"seen",seen,"mastery",mastery,"recentCorrect",recentCorrect,"recentCount",recentEvidence.length(),"recentItemCount",recent,
                "targetDifficulty",target,"difficulty",item.optInt("difficulty"),"reason",reason,"goal",goal,"factors",scores,"strategy",strategy,
                "scoreUsedForSelection",!"random".equals(strategy)&&!"diagnostic".equals(strategy)&&!"card".equals(strategy));
    }
    public synchronized String sessionNotice(long id) throws JSONException { return sessionNotice(id,0); }
    public synchronized String sessionNotice(long id,int requested) throws JSONException {
        JSONObject session=one("SELECT * FROM session WHERE id=?",""+id);
        if(session==null)return "没有符合条件的题目。请添加内容或调整练习范围。";
        JSONArray plan=new JSONArray(session.getString("plan"));
        int recent=0;
        for(int i=0;i<plan.length();i++)if(count("SELECT COUNT(*) n FROM attempt WHERE item_id=? AND skill=? AND at>? AND at<?",""+plan.getLong(i),session.optString("mode"),""+(session.optLong("created_at")-86400000L),""+session.optLong("created_at"))>0)recent++;
        String message=requested>plan.length()?"符合条件的题目只有 "+plan.length()+" 条，已按实际数量安排，不重复填充。":"本轮 "+plan.length()+" 条，进度自动保存。";
        if(recent>0&&!"random".equals(session.optString("strategy")))message+="部分题目近24小时做过；已优先采用非近期题，数量不足时回退复习。";
        return message;
    }
    /** Refresh unanswered positions from the eligible pool; committed evidence and the current item stay fixed. */
    private void rerankRemaining(JSONObject session,JSONArray plan,int position,long now) throws JSONException {
        String strategy=session.optString("strategy");
        if("random".equals(strategy)||"diagnostic".equals(strategy)||position+1>=plan.length())return;
        Set<Long> used=new HashSet<>();
        for(int i=0;i<=position;i++)used.add(plan.getLong(i));
        JSONArray evidence=rows("SELECT item_id FROM attempt WHERE session_id=?",""+session.optLong("id"));
        for(int i=0;i<evidence.length();i++)used.add(evidence.optJSONObject(i).optLong("item_id"));
        List<JSONObject> remaining=new ArrayList<>();
        for(JSONObject item:candidates(session.optLong("library_id"),session.getString("mode"),strategy,session.optLong("target_point"),now))
            if(!used.contains(item.optLong("id")))remaining.add(item);
        // A strict recent-item partition avoids repeats when there is another eligible question.
        remaining.sort((a,b)-> {
            int novelty=Boolean.compare(a.optInt("recent")>0,b.optInt("recent")>0);
            return novelty!=0?novelty:Double.compare(b.optDouble("priority"),a.optDouble("priority"));
        });
        int required=plan.length()-position-1;
        Set<Long> selected=new HashSet<>();
        for(int i=0;i<Math.min(required,remaining.size());i++)selected.add(remaining.get(i).optLong("id"));
        // Archiving content mid-session must not shorten or corrupt an already saved plan.
        for(int i=position+1;remaining.size()<required&&i<plan.length();i++) {
            long id=plan.getLong(i);
            if(used.contains(id)||selected.contains(id))continue;
            JSONObject previous=one("SELECT * FROM item WHERE id=?",""+id);
            if(previous==null)throw new JSONException("练习内容已不存在，请重新开始");
            remaining.add(previous);selected.add(id);
        }
        if(remaining.size()<required)throw new JSONException("练习题目不足，请重新打开知识库");
        for(int i=0;i<required;i++)plan.put(position+1+i,remaining.get(i).getLong("id"));
        edit("session",session.getLong("id"),obj("plan",plan.toString()));
    }
    public synchronized void submit(long session,int position,long item,String prompt,String expected,String response,boolean correct,int confidence,String skill,long elapsed) throws JSONException  {
        SQLiteDatabase db=getWritableDatabase();
        db.beginTransaction();
        try  {
            JSONObject ss=one("SELECT * FROM session WHERE id=?",""+session);
            if(ss==null||ss.optInt("finished")!=0||ss.optInt("position")!=position) throw new JSONException("练习位置已改变，请重新打开");
            JSONArray plan=new JSONArray(ss.getString("plan"));
            if(position>=plan.length()||plan.getLong(position)!=item||!ss.getString("mode").equals(skill))throw new JSONException("练习内容不匹配");
            if(one("SELECT id FROM attempt WHERE session_id=? AND position=?",""+session,""+position)!=null)  {
                db.setTransactionSuccessful();
                return;
            }
            long now=System.currentTimeMillis();
            long aid=insert("attempt",obj("session_id",session,"position",position,"item_id",item,"prompt",prompt,"expected",expected,"response",response,"correct",correct?1:0,"confidence",confidence,"skill",skill,"elapsed_ms",Math.max(0,elapsed),"at",now));
            if(skill.equals("question"))  {
                JSONArray links=rows("SELECT point_id FROM item_point WHERE item_id=?",""+item);
                for(int i=0;i<links.length();i++) {
                    long pid=links.getJSONObject(i).getLong("point_id");
                    insert("attempt_point",obj("attempt_id",aid,"point_id",pid));
                    updateState(aid,pid,"knowledge",correct,confidence,now);
                }
            }
            else updateState(aid,item,skill,correct,confidence,now);
            rerankRemaining(ss,plan,position,now);
            db.setTransactionSuccessful();
        }
        finally  {
            db.endTransaction();
        }
    }
    private void updateState(long attempt,long id,String skill,boolean correct,int confidence,long now)  {
        JSONObject s=state(id,skill);
        int days=LearningEngine.nextInterval(s.optInt("interval_days"),correct,confidence);
        LearningEngine.Trace trace=LearningEngine.trace(s.optDouble("mastery"),correct,confidence);
        double after=trace.after;
        insert("state_change",obj("attempt_id",attempt,"owner_id",id,"skill",skill,"before_value",s.optDouble("mastery"),"after_value",after,"at",now,
                "guess",trace.guess,"slip",trace.slip,"learn",trace.learn,"posterior",trace.posterior,"model_version",trace.modelVersion));
        ContentValues v=values(obj("owner_id",id,"skill",skill,"mastery",after,"seen",s.optInt("seen")+1,"last_at",now,"due_at",now+days*86400000L,"interval_days",days));
        getWritableDatabase().insertWithOnConflict("state",null,v,SQLiteDatabase.CONFLICT_REPLACE);
    }
    public synchronized void advance(long session) throws JSONException  {
        JSONObject s=one("SELECT * FROM session WHERE id=?",""+session);
        int p=s.getInt("position");
        if(count("SELECT COUNT(*) n FROM attempt WHERE session_id=? AND position=?",""+session,""+p)==0) return;
        int length=new JSONArray(s.getString("plan")).length();
        SQLiteDatabase sql=getWritableDatabase();
        sql.beginTransaction();
        try  {
            edit("session",session,obj("position",p+1,"finished",p+1>=length?1:0));
            if(p+1>=length) {
                sql.execSQL("UPDATE task SET completed=1 WHERE practice_session=?",new Object[] {
                    session
                }
                );
                JSONObject task=one("SELECT * FROM task WHERE practice_session=? AND stage='application'",""+session);
                if(task!=null) {
                    JSONObject source=one("SELECT * FROM session WHERE id=?",""+task.optLong("source_session"));
                    sql.execSQL("UPDATE task SET due_at=? WHERE source_session=? AND stage='delayed'",new Object[] {
                        reviewDeadline(source,task.optLong("point_id"),System.currentTimeMillis()),task.optLong("source_session")
                    });
                }
                createTasks(session);
            }
            sql.setTransactionSuccessful();
        }
        finally {
            sql.endTransaction();
        }
    }
    public synchronized void createTasks(long session) throws JSONException  {
        JSONObject s=one("SELECT * FROM session WHERE id=?",""+session);
        if(s==null||s.optInt("finished")==0||count("SELECT COUNT(*) n FROM task WHERE practice_session=?",""+session)>0)return;
        JSONObject weakest=one("SELECT p.point_id,MIN(st.mastery) mastery FROM attempt_point p JOIN attempt a ON a.id=p.attempt_id JOIN state st ON st.owner_id=p.point_id AND st.skill='knowledge' WHERE a.session_id=? GROUP BY p.point_id ORDER BY mastery LIMIT 1",""+session);
        long point=weakest==null?0:weakest.optLong("point_id");
        long now=System.currentTimeMillis();
        for(String stage:new String[] {
            "concept","basic","application","delayed"
        }
        )  {
            ContentValues v=values(obj("source_session",session,"library_id",s.optLong("library_id"),"point_id",point,"stage",stage,"due_at",stage.equals("delayed")?reviewDeadline(s,point,now):now));
            getWritableDatabase().insertWithOnConflict("task",null,v,SQLiteDatabase.CONFLICT_IGNORE);
        }
    }
    private long reviewDeadline(JSONObject session,long point,long now) {
        long due=0;
        if(session!=null&&"question".equals(session.optString("mode"))&&point>0)
            due=state(point,"knowledge").optLong("due_at");
        else if(session!=null) {
            JSONObject estimate=one("SELECT MIN(st.due_at) due_at FROM state st JOIN attempt a ON a.item_id=st.owner_id AND a.skill=st.skill WHERE a.session_id=?",""+session.optLong("id"));
            due=estimate==null?0:estimate.optLong("due_at");
        }
        return Math.max(now+86400000L,due);
    }
    public synchronized void archiveLibrary(long id)  {
        SQLiteDatabase db=getWritableDatabase();
        db.beginTransaction();
        try  {
            edit("library",id,obj("archived",1));
            db.execSQL("UPDATE session SET finished=2 WHERE library_id=? AND finished=0",new Object[] {
                id
            }
            );
            db.setTransactionSuccessful();
        }
        finally {
            db.endTransaction();
        }
    }
    public synchronized JSONObject backup() throws JSONException  {
        JSONObject root=obj("format","zhixue-backup","version",4,"at",System.currentTimeMillis());
        for(String t:TABLES)root.put(t,rows("SELECT * FROM "+t));
        return root;
    }
    private static final String[] TABLES= {
        "library","point","item","item_point","state","session","attempt","attempt_point","self_rating","reference","state_change","task","ai_source"
    }
    ;
    public synchronized void restore(JSONObject root) throws JSONException  {
        if(!"zhixue-backup".equals(root.getString("format"))||root.getInt("version")<1||root.getInt("version")>4)throw new JSONException("备份版本不支持");
        SQLiteDatabase db=getWritableDatabase();
        db.beginTransaction();
        try  {
            for(int i=TABLES.length-1;i>=0;i--)db.delete(TABLES[i],null,null);
            for(String t:TABLES)  {
                JSONArray rs=(root.getInt("version")<4&&t.equals("ai_source"))||(root.getInt("version")==1&&(t.equals("state_change")||t.equals("task")))?new JSONArray():root.getJSONArray(t);
                for(int i=0;i<rs.length();i++)  {
                    JSONObject row=rs.getJSONObject(i);
                    if(t.equals("reference"))continue;
                    insert(t,row);
                }
            }
            try(Cursor c=db.rawQuery("PRAGMA foreign_key_check",null)) {
                if(c.moveToFirst())throw new JSONException("备份关联数据不完整");
            }
            db.setTransactionSuccessful();
        }
        finally {
            db.endTransaction();
        }
    }
}
