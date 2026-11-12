"""Evidence-backed memory cues for recurring computer-system concepts.

A cue is emitted only when its fact matches source text.
These rules are examples of mnemonic construction, not a document identity check.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Fact:
    cue: str
    point: str
    meaning: str
    pattern: str


@dataclass(frozen=True)
class Rule:
    title: str
    facts: tuple[Fact, ...]


RULES = (
    Rule('运算器', (
        Fact('ALU管运算', '算术逻辑单元（ALU）', '完成算术和逻辑运算。', r'ALU.{0,42}算[术数]运算.{0,8}逻辑运算'),
        Fact('AC供数存结果', '累加寄存器（AC）', '给 ALU 提供数据，暂存运算结果。', r'AC.{0,24}提供数据.{0,6}暂存运算结果'),
        Fact('DR中转数据', '数据缓冲寄存器（DR）', '在 CPU、内存和外设之间缓冲传送的数据。', r'数据缓冲寄存器.{0,64}数据传送.{0,8}中转'),
        Fact('PSW记条件', '状态条件寄存器（PSW）', '保存运算或测试产生的条件码。', r'PSW.{0,72}条件码'),
    )),
    Rule('控制器', (
        Fact('IR存当前', '指令寄存器（IR）', '保存当前执行的指令。', r'IR.{0,16}保存当前.{0,12}指令'),
        Fact('PC指下一条', '程序计数器（PC）', '指向将要执行的下一条指令。', r'程序计数器.{0,160}下一条指令的地址'),
        Fact('AR记访问地址', '地址寄存器（AR）', '保存所访问的内存单元地址。', r'地址寄存器.{0,36}内存单元的地址'),
        Fact('ID看操作码', '指令译码器（ID）', '解析指令的操作码字段。', r'指令译码器.{0,24}操作码字段'),
    )),
    Rule('单位与地址', (
        Fact('八位成一字节', '位与字节', '一个字节等于八位。', r'1\s*B\s*=\s*8\s*bit'),
        Fact('存储换级看进制', '存储单位', '讲义的存储单位题按 1024 进位。', r'1\s*KB\s*=\s*1024\s*B'),
        Fact('首尾都算，大减小加一', '连续地址计数', '连续地址区间包含首尾时，单元数是末地址减首地址再加 1。', r'大\s*减\s*小\s*再?\s*加\s*1'),
    )),
    Rule('原反补移码', (
        Fact('负数反码留符号、其余翻', '反码', '负数反码由原码保持符号位、其余位取反得到。', r'负数的反码.{0,24}除符号位以外.{0,15}取反'),
        Fact('反码加一成补码', '补码', '负数的补码在反码基础上加一。', r'负数的补码.{0,25}反码.{0,16}加\s*1'),
        Fact('补码翻符号得移码', '移码', '讲义的移码用同位宽补码翻转最高位得到。', r'移码.{0,22}补码.{0,18}符号位取反'),
        Fact('原反两个零，补移一个零', '零的编码', '原码和反码区分正负零，补码和移码各只有一个零编码。', r'补码和移码.{0,30}相同的编码[^\n]*\s*原码和反码.{0,30}两个编码'),
    )),
    Rule('浮点数', (
        Fact('小阶向大阶，小尾向右移', '对阶', '加减先对阶，较小阶码向较大阶码对齐，对应尾数右移。', r'小阶向大阶对齐.{0,8}尾数右移'),
        Fact('阶码管范围，尾数管精度', '浮点数范围与精度', '阶码决定范围，尾数决定精度。', r'范围由阶码决定.{0,26}精度由尾数决定'),
    )),
    Rule('寻址', (
        Fact('立即给数', '立即寻址', '指令本身包含操作数。', r'立即寻址.{0,10}操作数.{0,12}包含在指令中'),
        Fact('直接给址', '直接寻址', '指令直接给出内存中的操作数地址。', r'直接寻址.{0,45}指令中直接给出.{0,30}地址'),
        Fact('寄存器给数', '寄存器寻址', '从指令指定的寄存器取操作数。', r'寄存器寻址.{0,18}操作数存放在某一寄存器'),
        Fact('寄间先取址', '寄存器间接寻址', '先从寄存器取地址，再去内存取操作数。', r'寄存器间接寻址.{0,85}地址在某个\s*寄存器'),
    )),
    Rule('校验码', (
        Fact('奇偶数一，检奇不纠', '奇偶校验', '能检出奇数个位翻转，不能纠错。', r'奇偶校验.{0,42}奇数位错误.{0,12}不能纠错'),
        Fact('海明分组，能纠一位', '海明码', '讲义中的基本海明码利用分组奇偶性，最小码距为 3，可纠一位错。', r'海明码.{0,55}奇偶性.{0,40}码距为\s*3'),
        Fact('CRC模二除，余数接末尾', '循环冗余校验', '用模二运算求校验值，校验位接在数据之后。', r'数据位后跟.{0,12}校验位.{0,65}模\s*2运算'),
    )),
    Rule('RISC 与 CISC', (
        Fact('精简少而齐，复杂多而变', '指令特点', '讲义对照表中，RISC 指令种类少、长度固定；CISC 指令种类多、长度可变。', r'指令种类\s*\|\s*少、精简\s*\|\s*多、丰富[\s\S]{0,55}指令长度\s*\|\s*固定\s*\|\s*变化'),
        Fact('精简少寻址，复杂方式多', '寻址方式', '讲义对照表中，RISC 寻址方式较少，CISC 较多。', r'寻址方式\s*\|\s*少\s*\|\s*复杂多样'),
    )),
    Rule('流水线', (
        Fact('首条走全程，后续隔一拍', '流水线总时间', '连续执行且无停顿时，总时间等于首条耗时加上其余各条的节拍。', r'流水线执行时间.{0,28}一条指令执行的时间.{0,20}最长时间段'),
        Fact('节拍看最慢', '流水线节拍', '最长操作时间决定流水线的节拍。', r'流水线的操作周期为长操作时间'),
        Fact('加速比用旧时间除新时间', '加速比', '顺序执行时间除以流水线执行时间。', r'加速比\s*=\s*不采用流水线的执行时间\s*/\s*采用流水线的执行时间'),
    )),
    Rule('存储与 Cache', (
        Fact('主存DRAM要刷新', 'DRAM', '动态存储器用于主存，需要定期刷新。', r'DRAM.{0,35}构成主存.{0,12}需要周期性地刷新'),
        Fact('缓存用SRAM', 'SRAM', '静态存储器可用作 Cache。', r'SRAM.{0,30}构成Cache'),
        Fact('直映位置定', '直接映像', '每个主存块有固定的映射位置。', r'直接映像.{0,24}关系固定'),
        Fact('全相任意放', '全相联映像', '主存块可映射到 Cache 的任意块。', r'全相联映像.{0,55}可以映射到Cache中的任意一块'),
        Fact('组相两头折中', '组相联映像', '介于直接映像和全相联之间。', r'组相联.{0,40}直接映像与全相联映像的折中'),
    )),
    Rule('中断与输入输出', (
        Fact('向量指入口', '中断向量', '提供中断服务程序的入口地址。', r'中断向量.{0,20}中断服务程序的入口地址'),
        Fact('保存现场为返回', '保存现场', '保存现场是为了中断处理后正确返回原程序。', r'保存现场.{0,20}正确返回原程序'),
        Fact('查询一直问', '程序查询', 'CPU 轮询检查外设。', r'CPU需要一直轮询检查'),
        Fact('中断等通知', '中断驱动', '设备主动通过中断信号报告完成。', r'通过中断信号主动\s*向CPU报告.{0,14}操作已完成'),
        Fact('DMA成块搬', 'DMA', 'DMA 数据传送以块为单位。', r'一次读写的单位为.{0,4}块'),
    )),
    Rule('公钥加密与数字签名', (
        Fact('加密找收方，公钥锁、私钥开', '公钥加密', '接收方公钥加密，接收方私钥解密。', r'接收方的公钥加密.{0,12}接收方的私钥解密'),
        Fact('签名找发方，私钥签、公钥验', '数字签名', '发送方私钥签名，发送方公钥验证。', r'发送方的私钥签名.{0,24}发送方的公钥验证'),
    )),
    Rule('总线', (
        Fact('总线分数、址、控', '总线分类', '三类是数据总线、地址总线和控制总线。', r'数据总线、地址总线和控制总线'),
        Fact('PCI并行', 'PCI', '讲义中的传统 PCI 使用并行传输。', r'PCI总线[^。\n]{0,65}并行传输'),
        Fact('PCIe点对点串行', 'PCI Express', 'PCI Express 使用点对点串行连接。', r'PCI-E[^。\n]{0,15}点对点串行'),
    )),
    Rule('系统可靠度', (
        Fact('串联全都好，成功率相乘', '串联系统', '部件独立时，所有部件正常才成功，可靠度为各部件可靠度之积。', r'串联系统的可靠性模型[\s\S]{0,100}R\s*='),
        Fact('并联怕全坏，一减全坏率', '并联系统', '部件独立时，系统可靠度等于 1 减去各部件均失败的概率。', r'只\s*要有一个子系统正常工作.{0,24}系统就能正常工作'),
    )),
)


def supported_cards(sections):
    lines = []
    for section in sections:
        raw = section['text']
        # Normalize spaces for matching; keep verbatim spans for the user to inspect.
        for match in re.finditer(r'[^\n]+', raw):
            start = match.start()
            end = min(len(raw), match.end() + 100)
            quote = raw[start:end].strip()
            lines.append((section, quote))
    cards = []
    for rule in RULES:
        anchors = []
        for fact in rule.facts:
            for section, quote in lines:
                found = re.search(fact.pattern, quote, re.IGNORECASE)
                if not found:
                    continue
                anchors.append({'point': fact.point, 'cue': fact.cue, 'meaning': fact.meaning,
                                'evidence': found.group(0), 'source': section['source'],
                                'location': section['location'], 'ocr': section['extraction'] == 'ocr'})
                break
        if len(anchors) >= 2:
            cards.append({'title': rule.title, 'mnemonic': '，'.join(a['cue'] for a in anchors), 'anchors': anchors})
    return cards
