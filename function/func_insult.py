import random

class InsultGenerator:
    """
    生成贴吧风格的骂人话术
    """
    
    # 贴吧风格骂人话术模板
    INSULT_TEMPLATES = [
        "{target}，你这想法属实有点抽象，建议回炉重造。",
        "不是吧，{target}，这都能说出来？大脑是用来思考的，不是用来长个儿的。",
        "乐，{target} 你成功逗笑了我，就像看猴戏一样。",
        "我说 {target} 啊，网上吵架没赢过，现实打架没输过是吧？",
        "{target}，听君一席话，浪费十分钟。",
        "给你个梯子，{target}，下个台阶吧，别搁这丢人现眼了。",
        "就这？{target}，就这？我还以为多大事呢。",
        "{target}，你是不是网线直连马桶的？味儿有点冲。",
        "讲道理，{target}，你这发言水平，在贴吧都活不过三楼。",
        "{target}，建议你去买两斤猪脑子煲汤喝，补补智商。",
        "说真的，{target}，你这智商要是放在好声音能把那四把椅子都转回来。",
        "{target}，放着好端端的智商不用，非得秀下限是吧？",
        "我看你是典型的脑子搭错弦，{target}，说话一套一套的。",
        "{target}，别整天搁这儿水经验了，你这水平也就适合到幼儿园门口卖糖水。",
        "你这句话水平跟你智商一样，{target}，都在地平线以下。",
        "就你这个水平，{target}，看王者荣耀的视频都能让你买错装备。",
        "{target}，整天叫唤啥呢？我没看《西游记》的时候真不知道猴子能说人话。",
        "我听懂了，{target}，你说的都对，可是能不能先把脑子装回去再说话？",
        "给{target}鼓个掌，成功把我逗乐了，这么多年的乐子人，今天是栽你手里了。"
    ]
    
    @staticmethod
    def generate_insult(target_name: str) -> str:
        """
        随机生成一句针对目标用户的骂人话术（贴吧风格）
        
        Args:
            target_name (str): 被骂的人的名字
            
        Returns:
            str: 生成的骂人语句
        """
        if not target_name or target_name.strip() == "":
            target_name = "那个谁"  # 兜底，防止名字为空
        
        template = random.choice(InsultGenerator.INSULT_TEMPLATES)
        return template.format(target=target_name)


def generate_random_insult(target_name: str) -> str:
    """
    随机生成一句针对目标用户的骂人话术（贴吧风格）
    函数封装，方便直接调用
    
    Args:
        target_name (str): 被骂的人的名字
        
    Returns:
        str: 生成的骂人语句
    """
    return InsultGenerator.generate_insult(target_name)