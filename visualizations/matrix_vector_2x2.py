from manimlib import *


class MatrixVector2x2(Scene):
    """Visualiza A·v para A = [[0, -1], [1, 0]] y v = (2, 1)."""

    def construct(self):
        matrix = "A = [[0, -1], [1, 0]]"
        initial_vector = "v = (2, 1)"
        result_vector = "A · v = (-1, 2)"

        title = Text("Multiplicación de una matriz 2×2 por un vector 2×1", font_size=34).to_edge(UP)
        formula = VGroup(
            Text(matrix, font_size=28),
            Text(initial_vector, font_size=28),
            Text(result_vector, font_size=28),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.13).to_corner(UL).shift(DOWN * 0.75)

        axes = Axes(
            x_range=(-4, 4, 1),
            y_range=(-3, 3, 1),
            width=8.2,
            height=5.7,
            axis_config={"include_tip": True},
        ).shift(RIGHT * 1.35 + DOWN * 0.5)

        origin = axes.c2p(0, 0)
        vector_v = Arrow(origin, axes.c2p(2, 1), buff=0, color=YELLOW, stroke_width=7)
        vector_av = Arrow(origin, axes.c2p(-1, 2), buff=0, color=BLUE, stroke_width=7)
        label_v = Text("v = (2, 1)", font_size=25, color=YELLOW).next_to(vector_v.get_end(), RIGHT, buff=0.1)
        label_av = Text("A · v = (-1, 2)", font_size=25, color=BLUE).next_to(vector_av.get_end(), LEFT, buff=0.1)
        initial_note = Text("vector inicial", font_size=22, color=YELLOW).to_edge(DOWN).shift(LEFT * 2.2)
        result_note = Text("vector resultante", font_size=22, color=BLUE).to_edge(DOWN).shift(RIGHT * 2.2)

        self.play(Write(title), ShowCreation(axes))
        self.play(Write(formula[0]), Write(formula[1]))
        self.play(GrowArrow(vector_v), Write(label_v), FadeIn(initial_note))
        self.wait(1)
        self.play(Write(formula[2]))
        self.play(Transform(vector_v, vector_av), Transform(label_v, label_av), Transform(initial_note, result_note))
        self.wait(2)
