TEMPLATE = {
    "name": "镇志",
    "description": "镇级地方志标准篇目",
    "outline_template": [
        {"title": "序", "level": 0, "required": True},
        {"title": "凡例", "level": 0, "required": True},
        {"title": "概述", "level": 1, "required": True},
        {"title": "大事记", "level": 1, "required": True},
        {
            "title": "建置",
            "level": 1,
            "children": [
                {"title": "位置地域", "level": 2},
                {"title": "建置沿革", "level": 2},
                {"title": "行政村居", "level": 2},
            ],
        },
        {
            "title": "自然环境",
            "level": 1,
            "children": [
                {"title": "地质地貌", "level": 2},
                {"title": "气候水文", "level": 2},
                {"title": "自然资源", "level": 2},
            ],
        },
        {
            "title": "人口",
            "level": 1,
            "children": [
                {"title": "人口状况", "level": 2},
                {"title": "人口变动", "level": 2},
                {"title": "计划生育", "level": 2},
            ],
        },
        {
            "title": "基础设施",
            "level": 1,
            "children": [
                {"title": "交通运输", "level": 2},
                {"title": "水利电力", "level": 2},
                {"title": "邮电通信", "level": 2},
                {"title": "城乡建设", "level": 2},
            ],
        },
        {
            "title": "经济",
            "level": 1,
            "children": [
                {"title": "农业", "level": 2},
                {"title": "工业", "level": 2},
                {"title": "商贸服务业", "level": 2},
                {"title": "财政金融", "level": 2},
            ],
        },
        {
            "title": "政治",
            "level": 1,
            "children": [
                {"title": "中共基层组织", "level": 2},
                {"title": "基层政权", "level": 2},
                {"title": "群众团体", "level": 2},
            ],
        },
        {
            "title": "文化",
            "level": 1,
            "children": [
                {"title": "教育", "level": 2},
                {"title": "文化体育", "level": 2},
                {"title": "医疗卫生", "level": 2},
                {"title": "文物胜迹", "level": 2},
            ],
        },
        {
            "title": "社会",
            "level": 1,
            "children": [
                {"title": "民政社保", "level": 2},
                {"title": "人民生活", "level": 2},
                {"title": "民俗风情", "level": 2},
            ],
        },
        {
            "title": "人物",
            "level": 1,
            "children": [
                {"title": "人物传略", "level": 2},
                {"title": "人物简介", "level": 2},
                {"title": "荣誉名录", "level": 2},
            ],
        },
        {"title": "附录", "level": 1, "required": True},
        {"title": "编纂始末", "level": 0, "required": True},
        {"title": "后记", "level": 0, "required": True},
    ],
    "editorial_notes_template": (
        "一、本志以科学发展观为指导，全面记述镇域自然、政治、经济、文化、社会的发展历程。\n"
        "二、本志上限力求追溯事物发端，下限至编纂年份。\n"
        "三、本志采用述、记、志、传、图、表、录等体裁，以志为主。\n"
        "四、本志引文均标注来源，数据以统计部门数据为准。"
    ),
}
