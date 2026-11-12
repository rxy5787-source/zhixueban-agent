"""Original, parameterized calculations for Software Designer practice."""
from fractions import Fraction
from random import Random

MODE = 'software_designer_calculation'
METHOD = 'software_designer_calculation_v1'
REFERENCE = 'https://www.tup.tsinghua.edu.cn/bookscenter/book_07552001.html'


def complement(rng):
    bits = rng.choice((6, 7, 8, 10))
    half = 1 << (bits - 1)
    magnitude = rng.choice([value for value in range(2, half) if value != half // 2])
    code = (half << 1) - magnitude
    stem = f'某处理器用 {bits} 位补码存放有符号整数。寄存器内容为 {code:0{bits}b}，其十进制值是多少？'
    return stem, -magnitude, [code, -(code - half), 1 - magnitude], (
        f'按无符号数读出 {code}，最高位为 1，按 {bits} 位补码解释应减去 2^{bits}。'
        f'{code} − {half << 1} = {-magnitude}。直接读成 {code} 会漏掉符号位的负权。'
    )


def overflow(rng):
    bits = rng.choice((6, 7, 8, 10))
    half = 1 << (bits - 1)
    sign = rng.choice((-1, 1))
    left, right = (sign * rng.randint(half // 2 + 1, half - 2) for _ in range(2))
    total = left + right
    raw = total % (half << 1)
    wrapped = raw - (half << 1) if raw >= half else raw
    limit = half - 1 if sign > 0 else -half
    stem = (f'在 {bits} 位有符号补码加法器中计算 ({left}) + ({right})。硬件只保留低 {bits} 位，'
            '不做饱和处理。将保留位按补码解释，结果和溢出状态是什么？')
    return stem, f'{wrapped}，有溢出', [f'{wrapped}，无溢出', f'{limit}，有溢出', f'{total}，无溢出'], (
        f'数学和为 {total}，超过 {bits} 位补码可表示的范围 [{-half}, {half - 1}]，因此溢出。'
        f'保留低位得到 {raw:0{bits}b}，重新按有符号补码解释为 {wrapped}。'
    )


def floating(rng):
    bits = rng.choice((3, 4, 5))
    exponent = rng.choice((-4, -3, -2, -1, 1, 2, 3))
    fraction = rng.randrange(1, 1 << bits)
    sign = rng.randrange(2)
    mantissa = Fraction(fraction, 1 << bits)
    scale = Fraction(2) ** exponent
    signed_scale = (-1) ** sign * scale
    answer = signed_scale * mantissa
    stem = (f'一种浮点格式按「尾数符号 | 4 位补码阶码 | {bits} 位纯小数」存储。'
            f'数值为 (−1)^s × (0.f)₂ × 2^E，无隐含的整数位。编码 {sign} | {exponent & 15:04b} | '
            f'{fraction:0{bits}b} 表示的数值是多少？')
    return stem, answer, [-answer, answer * 2, signed_scale * (1 + mantissa)], (
        f'阶码按 4 位补码解码得到 E = {exponent}。小数部分是 {fraction}/{1 << bits}，'
        f'即 {mantissa}。带入符号位 {sign}，(−1)^{sign} × {mantissa} × 2^{exponent} = {answer}。'
    )


def graph(rng):
    edges = rng.randint(4, 45)
    vertices = next(n for n in range(2, 12) if n * (n - 1) // 2 >= edges)
    stem = (f'某无向简单图的邻接矩阵在严格上三角区域共有 {edges} 个 1。'
            '若构造一个边数相同的无向简单图，至少需要多少个顶点？')
    return stem, vertices, [vertices - 1, vertices + 1, vertices + 2], (
        f'无向图的每条边在严格上三角区域只记一次，所以图有 {edges} 条边。'
        f'{vertices - 1} 个顶点最多容纳 {(vertices - 1) * (vertices - 2) // 2} 条边，'
        f'{vertices} 个顶点最多容纳 {vertices * (vertices - 1) // 2} 条边，最少需要 {vertices} 个顶点。'
    )


def cache(rng):
    address_bits = rng.choice((20, 24, 28, 32))
    offset_bits = rng.randrange(4, 8)
    index_bits = rng.randrange(max(4, 10 - offset_bits), 10)
    capacity = (1 << (offset_bits + index_bits)) // 1024
    block = 1 << offset_bits
    tag_bits = address_bits - offset_bits - index_bits
    stem = (f'某机器按字节编址，物理地址为 {address_bits} 位。直接映射 Cache 的数据容量为 {capacity} KiB，'
            f'每行存放 {block} 字节。主存地址中的标记（Tag）占多少位？')
    return stem, tag_bits, [address_bits - index_bits, tag_bits - 1, tag_bits + 1], (
        f'块内偏移需 log₂({block}) = {offset_bits} 位。Cache 有 {capacity * 1024} ÷ {block} = {1 << index_bits} 行，'
        f'行索引需 {index_bits} 位。标记位数 = {address_bits} − {index_bits} − {offset_bits} = {tag_bits}。'
    )


TOPICS = {
    'complement': ('补码表示', '简单', '补码最高位的权值为负，其余位的权值和无符号整数相同。', complement),
    'overflow': ('补码运算与溢出', '中等', '固定位宽补码运算需同时判断数学结果的范围和截断后的机器值。', overflow),
    'floating': ('浮点表示', '中等', '浮点值由符号、阶码和尾数共同决定，应按题设位布局解码。', floating),
    'graph': ('无向图与邻接矩阵', '中等', '无向简单图的邻接矩阵对称，每条边在严格上三角区域计一次。', graph),
    'cache': ('Cache 地址映射', '中等', '直接映射地址由标记、行索引和块内偏移组成。', cache),
}


def generate(count, topic, seed):
    rng = Random(seed)
    topics = list(TOPICS) if topic == 'mixed' else [topic]
    points = [{'name': TOPICS[key][0], 'summary': TOPICS[key][2]} for key in topics[:count]]
    questions = []
    seen = set()
    for index in range(count):
        name, difficulty, rule, build = TOPICS[topics[index % len(topics)]]
        for _ in range(100):
            stem, correct, wrong, explanation = build(rng)
            if stem not in seen:
                break
        else:
            raise ValueError('暂时无法生成足量且不同的专项题')
        seen.add(stem)
        values = [str(value) for value in [correct, *wrong]]
        if len(values) != 4 or len(set(values)) != 4:
            raise ValueError('专项题选项校验失败')
        rng.shuffle(values)
        questions.append({
            'question': stem, 'options': dict(zip('ABCD', values)), 'answer': 'ABCD'[values.index(str(correct))],
            'explanation': explanation, 'knowledgePoint': name, 'difficulty': difficulty,
            'sourceFile': '软件设计师专项命题范围', 'sourceFileId': METHOD, 'sourceHash': '',
            'sourceLocation': name, 'evidenceQuote': rule, 'generationModel': METHOD, 'reviewModel': METHOD,
            'reviewMethod': METHOD, 'reviewStatus': 'rule_verified', 'questionConstruction': METHOD,
            'visualAssisted': False, 'textOnly': True, 'extraction': 'blueprint',
        })
    return questions, points
