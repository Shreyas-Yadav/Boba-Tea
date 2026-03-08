from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IdeaTemplate:
    title: str
    description: str
    difficulty: str
    source_query: str


@dataclass(frozen=True)
class ObjectTemplate:
    label: str
    ideas: tuple[IdeaTemplate, ...]


CATALOG: tuple[ObjectTemplate, ...] = (
    ObjectTemplate(
        label="plastic bottle",
        ideas=(
            IdeaTemplate(
                title="Self-watering planter",
                description="Turn the bottle into a compact herb planter with a water reservoir.",
                difficulty="easy",
                source_query="plastic bottle self watering planter diy",
            ),
            IdeaTemplate(
                title="Bird feeder",
                description="Cut feeding windows into the bottle and hang it outside for small birds.",
                difficulty="easy",
                source_query="plastic bottle bird feeder diy",
            ),
            IdeaTemplate(
                title="Desk organizer",
                description="Slice the bottle into cups for pens, clips, or charging cables.",
                difficulty="easy",
                source_query="plastic bottle desk organizer diy",
            ),
        ),
    ),
    ObjectTemplate(
        label="glass jar",
        ideas=(
            IdeaTemplate(
                title="Kitchen storage jar",
                description="Reuse the jar for dry goods, spices, or tea with a custom label.",
                difficulty="easy",
                source_query="glass jar kitchen storage diy",
            ),
            IdeaTemplate(
                title="Lantern holder",
                description="Add twine and a tealight insert to make a safe decorative lantern.",
                difficulty="medium",
                source_query="glass jar lantern diy",
            ),
            IdeaTemplate(
                title="Bathroom organizer",
                description="Use the jar to store cotton pads, brushes, or bath salts.",
                difficulty="easy",
                source_query="glass jar bathroom organizer diy",
            ),
        ),
    ),
    ObjectTemplate(
        label="cardboard box",
        ideas=(
            IdeaTemplate(
                title="Cable management station",
                description="Cut labeled slots into the box and use it to hide chargers and adapters.",
                difficulty="easy",
                source_query="cardboard box cable organizer diy",
            ),
            IdeaTemplate(
                title="Drawer divider set",
                description="Trim the box into panels to organize drawers and shelves.",
                difficulty="easy",
                source_query="cardboard drawer divider diy",
            ),
            IdeaTemplate(
                title="Toy storage bin",
                description="Wrap the box in paper or fabric and turn it into a lightweight storage bin.",
                difficulty="easy",
                source_query="cardboard storage bin diy",
            ),
        ),
    ),
    ObjectTemplate(
        label="tin can",
        ideas=(
            IdeaTemplate(
                title="Utensil holder",
                description="Sand the rim, paint the can, and reuse it as a kitchen utensil holder.",
                difficulty="easy",
                source_query="tin can utensil holder diy",
            ),
            IdeaTemplate(
                title="Mini planter",
                description="Convert the can into a succulent planter with drainage stones.",
                difficulty="easy",
                source_query="tin can planter diy",
            ),
            IdeaTemplate(
                title="Craft caddy",
                description="Group a few cans on a tray to organize brushes, scissors, and markers.",
                difficulty="easy",
                source_query="tin can desk organizer diy",
            ),
        ),
    ),
    ObjectTemplate(
        label="old t-shirt",
        ideas=(
            IdeaTemplate(
                title="Reusable tote bag",
                description="Cut and knot the shirt into a carry bag for groceries or books.",
                difficulty="easy",
                source_query="old t shirt tote bag diy",
            ),
            IdeaTemplate(
                title="Cleaning rags",
                description="Trim the shirt into washable cloths for dusting and general cleaning.",
                difficulty="easy",
                source_query="old t shirt cleaning rags diy",
            ),
            IdeaTemplate(
                title="Braided plant hanger",
                description="Use long strips of fabric to braid a hanging holder for a small pot.",
                difficulty="medium",
                source_query="old t shirt plant hanger diy",
            ),
        ),
    ),
)
