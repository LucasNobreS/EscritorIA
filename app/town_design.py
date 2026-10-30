"""Shared scenery, collision footprints and interactions for the town."""


def obj(
    id,
    kind,
    label,
    x,
    y,
    w,
    d,
    h=50,
    color="#bda182",
    actions=("inspect",),
    solid=True,
    **extra,
):
    return dict(
        id=id,
        kind=kind,
        label=label,
        x=x,
        y=y,
        w=w,
        d=d,
        h=h,
        color=color,
        actions=list(actions),
        solid=solid,
        **extra,
    )


def interiors(buildings):
    result = {}
    for b in buildings:
        if b["kind"] == "office":
            continue
        kind = b["kind"]
        col = b["color"]
        items = []

        def add(
            id,
            k,
            label,
            x,
            y,
            w,
            d,
            h=50,
            color=col,
            actions=("inspect",),
            solid=True,
            **kw,
        ):
            items.append(obj(id, k, label, x, y, w, d, h, color, actions, solid, **kw))

        home = kind in ("house", "apartments", "hotel")
        if home:
            add(
                "bed",
                "bed",
                "Cama · descansar",
                145,
                135,
                165,
                235,
                65,
                "#9a8b83",
                ("rest", "inspect"),
            )
            add(
                "wardrobe",
                "wardrobe",
                "Guarda-roupa",
                140,
                520,
                160,
                55,
                105,
                "#aa9278",
                ("look", "inspect"),
            )
            add(
                "sofa",
                "sofa",
                "Sofá da sala",
                745,
                510,
                165,
                70,
                64,
                col,
                ("sit", "inspect"),
            )
            add(
                "coffee",
                "coffee",
                "Mesa de centro",
                615,
                560,
                100,
                65,
                34,
                "#c6a17b",
                ("read", "inspect"),
            )
            add(
                "dining",
                "table",
                "Mesa de refeições",
                490,
                200,
                150,
                100,
                48,
                "#c7a98c",
                ("drink", "inspect"),
            )
            add(
                "kitchen",
                "kitchen",
                "Cozinha · preparar café",
                755,
                120,
                205,
                65,
                80,
                "#a9b8ad",
                ("drink", "inspect"),
            )
            add(
                "shelf",
                "shelf",
                "Estante de livros",
                865,
                285,
                65,
                125,
                115,
                "#b49b80",
                ("read", "inspect"),
            )
            add(
                "lamp",
                "lamp",
                "Luminária da sala",
                700,
                430,
                30,
                30,
                130,
                "#d8c69b",
                ("toggle", "inspect"),
            )
            add(
                "rug",
                "rug",
                "Tapete da sala",
                540,
                390,
                400,
                260,
                1,
                "#94ada6",
                ("inspect",),
                False,
            )
            add(
                "bed-rug",
                "rug",
                "Tapete do quarto",
                110,
                450,
                300,
                50,
                1,
                "#c5b18e",
                ("inspect",),
                False,
            )
            add(
                "partition",
                "partition",
                "Divisória do quarto",
                400,
                75,
                12,
                340,
                85,
                "#d8cbb7",
                ("inspect",),
            )
        elif kind == "books":
            for n, x in enumerate((130, 850)):
                add(
                    "shelf-" + str(n),
                    "shelf",
                    "Estante · escolher um livro",
                    x,
                    140,
                    90,
                    270,
                    150,
                    "#b09679",
                    ("read", "inspect"),
                )
            add(
                "reading",
                "table",
                "Mesa de leitura",
                210,
                555,
                190,
                90,
                48,
                "#c3a482",
                ("read", "inspect"),
            )
            add(
                "sofa",
                "sofa",
                "Poltrona de leitura",
                750,
                590,
                180,
                75,
                65,
                col,
                ("sit", "inspect"),
            )
            add(
                "counter",
                "counter",
                "Balcão da livraria",
                390,
                145,
                350,
                75,
                70,
                col,
                ("read", "inspect"),
                theme=kind,
            )
        elif kind == "arcade":
            for n, x in enumerate((150, 350, 700, 900)):
                add(
                    "arcade-" + str(n),
                    "arcade",
                    "Fliperama · jogar",
                    x,
                    170,
                    70,
                    90,
                    125,
                    ["#847fb3", "#8aada6", "#c99795", "#b3a46e"][n],
                    ("play", "inspect"),
                )
            add(
                "sofa",
                "sofa",
                "Sofá da galeria",
                720,
                600,
                220,
                75,
                65,
                col,
                ("sit", "inspect"),
            )
            add(
                "gallery",
                "display",
                "Painel de arte",
                140,
                580,
                240,
                45,
                120,
                col,
                ("read", "inspect"),
                theme=kind,
            )
        elif kind == "clothes":
            add(
                "rack-left",
                "rack",
                "Arara · experimentar um visual",
                140,
                160,
                230,
                70,
                130,
                "#9aabb4",
                ("look", "inspect"),
            )
            add(
                "rack-right",
                "rack",
                "Coleção de roupas",
                740,
                160,
                220,
                70,
                130,
                "#9aabb4",
                ("look", "inspect"),
            )
            add(
                "mirror",
                "mirror",
                "Espelho · personalizar personagem",
                800,
                500,
                110,
                30,
                160,
                "#c7b49b",
                ("look", "inspect"),
            )
            add(
                "counter",
                "counter",
                "Balcão do ateliê de moda",
                150,
                560,
                250,
                75,
                75,
                col,
                ("inspect",),
                theme=kind,
            )
        elif kind == "flowers":
            for n, (x, y) in enumerate(
                ((150, 160), (300, 160), (700, 160), (850, 160), (170, 540), (850, 540))
            ):
                add(
                    "plant-" + str(n),
                    "planter",
                    "Jardineira · cuidar das flores",
                    x,
                    y,
                    75,
                    65,
                    75,
                    ["#c1a18b", "#b8ad95", "#a3bab3"][n % 3],
                    ("water", "inspect"),
                )
            add(
                "counter",
                "counter",
                "Balcão da floricultura",
                400,
                150,
                280,
                75,
                75,
                col,
                ("read", "inspect"),
                theme=kind,
            )
            add(
                "bench",
                "bench",
                "Banco do jardim interno",
                210,
                665,
                160,
                45,
                58,
                "#b99476",
                ("sit", "inspect"),
            )
        elif kind == "hall":
            add(
                "counter",
                "counter",
                "Recepção da prefeitura",
                180,
                150,
                650,
                75,
                75,
                col,
                ("read", "inspect"),
                theme=kind,
            )
            add(
                "notice",
                "notice",
                "Mural da cidade",
                150,
                445,
                170,
                35,
                135,
                "#ac9273",
                ("read", "inspect"),
            )
            add(
                "sofa",
                "sofa",
                "Sala de espera",
                745,
                550,
                210,
                85,
                64,
                col,
                ("sit", "inspect"),
            )
        else:
            add(
                "counter",
                "counter",
                "Balcão · "
                + ("tomar um café" if kind in ("cafe", "bakery") else "ver produtos"),
                160,
                145,
                700,
                85,
                78,
                col,
                ("drink", "inspect")
                if kind in ("cafe", "bakery")
                else ("read", "inspect"),
                theme=kind,
            )
            if kind == "market":
                for n, x in enumerate((150, 800)):
                    add(
                        "display-" + str(n),
                        "display",
                        "Banca de produtos",
                        x,
                        410,
                        160,
                        170,
                        80,
                        "#b0ad83",
                        ("read", "inspect"),
                        theme="market",
                    )
            else:
                for n, (x, y) in enumerate(((210, 430), (735, 460), (210, 640))):
                    add(
                        "table-" + str(n),
                        "table",
                        "Mesa · fazer uma pausa",
                        x,
                        y,
                        120,
                        75,
                        48,
                        "#c9a884",
                        ("drink", "inspect"),
                    )
                    add(
                        "chair-" + str(n),
                        "chair",
                        "Cadeira",
                        x + 45,
                        y + 100,
                        42,
                        38,
                        63,
                        col,
                        ("sit", "inspect"),
                    )
            add(
                "shelf",
                "shelf",
                "Prateleira de " + ("pães" if kind == "bakery" else "utensílios"),
                890,
                135,
                65,
                200,
                145,
                "#bea17e",
                ("read", "inspect"),
                theme=kind,
            )
        if home or kind == "books":
            add(
                "tv",
                "tv",
                "TV · séries e programas",
                760 if home else 500,
                700 if home else 560,
                140,
                30,
                100,
                "#465c6e",
                ("catalog", "inspect"),
            )
        add(
            "plant-left",
            "plant",
            "Planta do ambiente",
            85,
            690,
            35,
            35,
            100,
            "#7eaa86",
            ("water", "inspect"),
        )
        add(
            "plant-right",
            "plant",
            "Planta junto à janela",
            985,
            340,
            35,
            35,
            100,
            "#7eaa86",
            ("water", "inspect"),
        )
        result[b["id"]] = {
            "theme": kind,
            "objects": items,
            "floor": "#cfbaa0" if home else "#d8d1be",
            "accent": col,
        }
    return result


def city_objects(buildings, map_data):
    objects = []

    def free(x, y):
        return (
            not any(
                b["x"] - 50 < x < b["x"] + b["w"] + 50
                and b["y"] - 50 < y < b["y"] + b["d"] + 70
                for b in buildings
            )
            and not any(
                a - 35 < x < a + w + 35 and b - 35 < y < b + d + 35
                for a, b, w, d in map_data["roads"]
            )
            and not any(
                a - 30 < x < a + w + 30 and b - 30 < y < b + d + 30
                for a, b, w, d in map_data["water"]
            )
        )

    for n in range(75):
        x = 90 + (n * 653) % 4000
        y = 70 + (n * 397) % 3000
        door_clear = not any(
            abs((x - y) - (b["door"][0] - b["door"][1])) < 100
            and 0 < (x + y) - (b["door"][0] + b["door"][1]) < 300
            for b in buildings
        )
        if free(x, y) and door_clear:
            objects.append(
                obj(
                    "tree-" + str(n),
                    "tree",
                    "Árvore da praça",
                    x - 16,
                    y - 16,
                    32,
                    32,
                    125,
                    "#77a681",
                    ("observe", "inspect"),
                )
            )
    for n, (x, y) in enumerate(((160, 2620), (3400, 2580), (1280, 1580))):
        objects.append(
            obj(
                "bench-" + str(n),
                "bench",
                "Banco da praça",
                x,
                y,
                130,
                40,
                58,
                "#ba9876",
                ("sit", "inspect"),
            )
        )
    for n in range(22):
        x = 140 + (n * 187) % 3900
        y = [530, 1330, 2130, 2890][n % 4]
        if not any(
            b["x"] - 25 < x < b["x"] + b["w"] + 25
            and b["y"] - 25 < y < b["y"] + b["d"] + 25
            for b in buildings
        ):
            objects.append(
                obj(
                    "lamp-" + str(n),
                    "lamp",
                    "Poste da rua",
                    x,
                    y,
                    14,
                    14,
                    140,
                    "#d9cead",
                    ("toggle", "inspect"),
                )
            )
    for n, (x, y) in enumerate(((820, 1930), (2020, 1190), (1350, 2370))):
        objects.append(
            obj(
                "notice-" + str(n),
                "notice",
                "Mural do bairro",
                x,
                y,
                110,
                30,
                125,
                "#b1997d",
                ("read", "inspect"),
            )
        )
    for n, (x, y) in enumerate(((500, 2590), (3490, 2680), (1480, 2030))):
        objects.append(
            obj(
                "planter-" + str(n),
                "planter",
                "Jardineira pública",
                x,
                y,
                65,
                55,
                70,
                "#c4ad92",
                ("water", "inspect"),
            )
        )
    objects.append(
        obj(
            "fountain",
            "fountain",
            "Fonte da Praça Ipê",
            400,
            2460,
            150,
            120,
            65,
            "#a5b9b6",
            ("toggle", "observe", "inspect"),
        )
    )
    objects.append(
        obj(
            "bin",
            "bin",
            "Lixeira seletiva",
            1370,
            1580,
            48,
            35,
            65,
            "#8aa598",
            ("clean", "inspect"),
        )
    )
    objects.append(
        obj(
            "bus-stop",
            "bus_stop",
            "Ponto de ônibus · mapa da região",
            3250,
            2130,
            190,
            55,
            145,
            "#8da6ae",
            ("read", "inspect"),
        )
    )
    for n, (x, y, c) in enumerate(
        ((750, 600, "#d7ba84"), (2300, 1400, "#a9bbc9"), (3200, 2200, "#bd919c"))
    ):
        objects.append(
            obj(
                "car-" + str(n),
                "car",
                "Carro estacionado",
                x,
                y,
                80,
                37,
                48,
                c,
                ("observe", "inspect"),
            )
        )
    return objects


ACTION_NAMES = {
    "catalog": "Consultar TVmaze",
    "inspect": "Examinar",
    "sit": "Sentar",
    "rest": "Descansar",
    "drink": "Tomar café",
    "read": "Ler / consultar",
    "water": "Regar",
    "toggle": "Ligar / desligar",
    "look": "Personalizar visual",
    "play": "Jogar",
    "observe": "Observar",
    "clean": "Recolher resíduos",
}


def inspect_text(item, scene):
    kind = item["kind"]
    return {
        "notice": "Aviso do bairro: aproveite as praças, visite os estabelecimentos e cuide dos espaços compartilhados.",
        "bus_stop": "Mapa da região: Vila Ipê ao norte, Aurora no centro e Costa Serena a leste. O escritório fica na avenida central.",
        "shelf": "Um acervo de leitura sobre arte, natureza e histórias da cidade. Você escolheu um volume para uma breve pausa.",
        "counter": "Uma pausa no passeio. Os serviços dos estabelecimentos são interações do jogo, sem cobrança ou pedidos reais.",
        "display": "Produtos e peças da vitrine. Você observou os detalhes da exposição.",
        "wardrobe": "Roupas e acessórios organizados. Personalize seu personagem sem alterar a identidade dos funcionários.",
        "arcade": "Desafio local: um passeio pela galeria rende uma partida e uma pontuação de brincadeira.",
        "fountain": "Água, pedra e o som imaginado da praça. A fonte pode ser ligada e desligada.",
        "bed": "Uma cama arrumada para descansar. Isso afeta apenas a pose do seu personagem, não a rotina da equipe.",
    }.get(
        kind,
        "Você observa "
        + item["label"].lower()
        + ". Um detalhe do ambiente que pode ser usado durante o passeio.",
    )
