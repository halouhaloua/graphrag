TEMPLATE = {
    "name": "县志",
    "description": "县级地方志标准篇目",
    "outline_template": [
        {"title": "序", "level": 0, "required": True},
        {"title": "凡例", "level": 0, "required": True},
        {"title": "概述", "level": 1, "required": True},
        {"title": "大事记", "level": 1, "required": True},
        {
            "title": "建置沿革",
            "level": 1,
            "children": [
                {"title": "位置面积", "level": 2},
                {"title": "建置沿革", "level": 2},
                {"title": "行政区划", "level": 2},
                {"title": "县城", "level": 2},
            ],
        },
        {
            "title": "自然环境",
            "level": 1,
            "children": [
                {"title": "地质地貌", "level": 2},
                {"title": "气候", "level": 2},
                {"title": "水文", "level": 2},
                {"title": "土壤植被", "level": 2},
                {"title": "自然资源", "level": 2},
                {"title": "自然灾害", "level": 2},
            ],
        },
        {
            "title": "人口",
            "level": 1,
            "children": [
                {"title": "人口规模", "level": 2},
                {"title": "人口构成", "level": 2},
                {"title": "人口变动", "level": 2},
                {"title": "计划生育", "level": 2},
            ],
        },
        {
            "title": "经济",
            "level": 1,
            "children": [
                {"title": "经济综述", "level": 2},
                {"title": "农业", "level": 2},
                {"title": "工业", "level": 2},
                {"title": "商贸服务业", "level": 2},
                {"title": "交通运输", "level": 2},
                {"title": "邮电通信", "level": 2},
                {"title": "财政税务", "level": 2},
                {"title": "金融保险", "level": 2},
            ],
        },
        {
            "title": "政治",
            "level": 1,
            "children": [
                {"title": "中国共产党地方组织", "level": 2},
                {"title": "人民代表大会", "level": 2},
                {"title": "人民政府", "level": 2},
                {"title": "人民政协", "level": 2},
                {"title": "纪检监察", "level": 2},
                {"title": "民主党派", "level": 2},
                {"title": "群众团体", "level": 2},
            ],
        },
        {
            "title": "文化",
            "level": 1,
            "children": [
                {"title": "教育", "level": 2},
                {"title": "科学技术", "level": 2},
                {"title": "文化艺术", "level": 2},
                {"title": "新闻出版", "level": 2},
                {"title": "广播电视", "level": 2},
                {"title": "体育", "level": 2},
                {"title": "文物古迹", "level": 2},
            ],
        },
        {
            "title": "社会",
            "level": 1,
            "children": [
                {"title": "民政", "level": 2},
                {"title": "劳动就业", "level": 2},
                {"title": "社会保障", "level": 2},
                {"title": "人民生活", "level": 2},
                {"title": "民族宗教", "level": 2},
                {"title": "风俗习惯", "level": 2},
            ],
        },
        {
            "title": "人物",
            "level": 1,
            "children": [
                {"title": "人物传", "level": 2},
                {"title": "人物简介", "level": 2},
                {"title": "人物表", "level": 2},
            ],
        },
        {
            "title": "艺文",
            "level": 1,
            "children": [
                {"title": "著作目录", "level": 2},
                {"title": "诗文选录", "level": 2},
                {"title": "碑记", "level": 2},
            ],
        },
        {
            "title": "附录",
            "level": 1,
            "required": True,
            "children": [
                {"title": "重要文献", "level": 2},
                {"title": "统计资料", "level": 2},
                {"title": "编纂始末", "level": 2},
            ],
        },
        {"title": "后记", "level": 0, "required": True},
    ],
    "editorial_notes_template": (
        "一、本志以马克思列宁主义、毛泽东思想、邓小平理论、"
        "'三个代表'重要思想、科学发展观为指导，坚持实事求是的原则。\n"
        "二、本志上限力求追溯事物发端，下限至编纂年份。\n"
        "三、本志采用述、记、志、传、图、表、录等体裁。\n"
        "四、本志纪年，中华人民共和国成立前用历史纪年括注公元，"
        "成立后用公元纪年。\n"
        "五、本志数据以统计部门数据为准，统计部门缺漏的采用业务部门数据。\n"
        "六、本志引文均标注来源。"
    ),
}
