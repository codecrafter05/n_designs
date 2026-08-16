"""Reset catalog tables and seed a realistic demo catalog.

Safe to re-run: wipes categories/products (and their images on disk), then rebuilds.
Does not touch users, orders, customers, or order_items.

Usage:
    source .venv/bin/activate && python scripts/seed_demo_data.py
"""
from __future__ import annotations

import shutil
import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from app.core.database import SessionLocal
from app.core.slugs import unique_slug
from app.models.category import Category
from app.models.customer import Customer
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductColor, ProductImage, ProductVariant
from app.models.user import User

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "static" / "img" / "Product"
UPLOAD_CATS = ROOT / "static" / "uploads" / "categories"
UPLOAD_PRODS = ROOT / "static" / "uploads" / "products"

# Filenames in static/img/Product/
CARRYALL_WORN = "louis-vuitton-carryall-mm--M46197_PM1_Worn view.avif"
CARRYALL_LOOK = "louis-vuitton-torebka-carryall-mm--M46197_PM1_Look view.webp"
SPEEDY = "louis-vuitton-speedy-bandouliere-25--M2A038_PM1_Worn view.avif"
PUMP_WORN = "louis-vuitton-luna-pump--AWE089PC78_PM1_Worn view.avif"
PUMP_CROP = "louis-vuitton-luna-pump--AWE089PC78_PM1_Cropped worn view.avif"
PULLOVER = "louis-vuitton-ribbed-knit-half-zip-pullover--FVKL60G4K846_PM1_Worn view.avif"
SKIRT = "louis-vuitton-woven-effect-knit-skirt--FVKZ24D9Z030_PM1_Worn view.avif"
BOMBER = "louis-vuitton-scarf-detail-bomber-jacket--FVOW80D6W150_PM1_Worn view.avif"
DENIM_JACKET = "louis-vuitton-hooded-monogram-denim-jacket--FVJA45UPI610_PM1_Worn view.avif"
SHORTS = "louis-vuitton-monogram-denim-mini-shorts--FVPT26UPI610_PM1_Worn view.avif"
EARRINGS_WORN = "louis-vuitton-lv-iconic-earrings--M00743_PM1_Worn view.avif"
EARRINGS_LOOK = "louis-vuitton-kolczyki-lv-iconic--M00743_PM1_Look view.avif"
SILK = "W_ACC_BC_SILKS2_JUNE26_DII.webp"
CHARM = "louis-vuitton-vivienne-fashionista-golf-bag-charm--M03986_PM1_Worn view.avif"

CLOTHING = ["XS", "S", "M", "L", "XL"]
SHOES = ["36", "37", "38", "39", "40"]
ONE = ["One Size"]

_copied: dict[str, str] = {}


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.001"))


def copy_image(filename: str, kind: str) -> str:
    key = f"{kind}:{filename}"
    if key in _copied:
        return _copied[key]
    src = DEMO / filename
    if not src.is_file():
        raise FileNotFoundError(src)
    dest_dir = UPLOAD_CATS if kind == "categories" else UPLOAD_PRODS
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{src.suffix.lower()}"
    shutil.copy2(src, dest_dir / name)
    url = f"/static/uploads/{kind}/{name}"
    _copied[key] = url
    return url


def wipe_upload_dir(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    removed = 0
    for item in path.iterdir():
        if item.name == ".gitkeep":
            continue
        if item.is_file():
            item.unlink()
            removed += 1
    return removed


def stock_map(sizes: list[str], zero: tuple[str, ...] = (), low: tuple[str, ...] = ()) -> dict[str, int]:
    out = {}
    for size in sizes:
        if size in zero:
            out[size] = 0
        elif size in low:
            out[size] = 3
        else:
            out[size] = 18
    return out


def variants_for(
    sizes: list[str],
    price,
    *,
    zero: tuple[str, ...] = (),
    low: tuple[str, ...] = (),
    sale_sizes: dict[str, object] | None = None,
) -> list[dict]:
    stocks = stock_map(sizes, zero, low)
    sale_sizes = sale_sizes or {}
    rows = []
    for size in sizes:
        row = {"size": size, "stock": stocks[size], "price": money(price)}
        if size in sale_sizes:
            row["sale"] = money(sale_sizes[size])
        rows.append(row)
    return rows


def add_category(db, name: str, parent: Category | None, image: str, order: int) -> Category:
    row = Category(
        name=name,
        slug=unique_slug(db, Category, name),
        parent_id=parent.id if parent else None,
        image_url=copy_image(image, "categories"),
        display_order=order,
    )
    db.add(row)
    db.flush()
    return row


def add_product(db, *, name: str, description: str, category: Category, images: list[str], colors: list[dict]) -> Product:
    min_price = min(money(v["price"]) for color in colors for v in color["variants"])
    product = Product(
        name=name,
        slug=unique_slug(db, Product, name),
        description=description,
        category_id=category.id,
        base_price=min_price,
        is_active=True,
    )
    db.add(product)
    db.flush()
    for index, filename in enumerate(images):
        db.add(
            ProductImage(
                product_id=product.id,
                image_url=copy_image(filename, "products"),
                sort_order=index,
            )
        )
    for color in colors:
        row = ProductColor(
            product_id=product.id,
            color_name=color["name"],
            color_hex=color["hex"],
        )
        db.add(row)
        db.flush()
        for variant in color["variants"]:
            db.add(
                ProductVariant(
                    product_color_id=row.id,
                    size=variant["size"],
                    stock_quantity=variant["stock"],
                    price=variant["price"],
                    compare_at_price=variant.get("sale"),
                )
            )
    return product


def seed(db) -> None:
    handbags = add_category(db, "Handbags", None, CARRYALL_LOOK, 0)
    shoes = add_category(db, "Shoes", None, PUMP_WORN, 1)
    rtw = add_category(db, "Ready-to-Wear", None, PULLOVER, 2)
    accessories = add_category(db, "Accessories", None, EARRINGS_LOOK, 3)

    totes = add_category(db, "Totes", handbags, CARRYALL_WORN, 0)
    shoulder = add_category(db, "Shoulder Bags", handbags, SPEEDY, 1)
    heels = add_category(db, "Heels", shoes, PUMP_CROP, 0)
    knitwear = add_category(db, "Knitwear", rtw, SKIRT, 0)
    outerwear = add_category(db, "Outerwear", rtw, BOMBER, 1)
    denim = add_category(db, "Denim", rtw, SHORTS, 2)
    jewelry = add_category(db, "Jewelry", accessories, EARRINGS_WORN, 0)
    scarves = add_category(db, "Scarves", accessories, SILK, 1)
    charms = add_category(db, "Charms", accessories, CHARM, 2)

    # --- Totes ---
    add_product(
        db,
        name="Manama Carryall",
        description=(
            "A structured everyday tote with a quiet monogram and room for a laptop, "
            "a compact, and a weekend scarf. Soft leather handles sit comfortably on the shoulder, "
            "and the interior is lined for the Gulf heat."
        ),
        category=totes,
        images=[CARRYALL_WORN, CARRYALL_LOOK],
        colors=[
            {"name": "Sand", "hex": "#C9C0AC", "variants": variants_for(ONE, 118, sale_sizes={"One Size": 96})},
            {"name": "Black", "hex": "#131210", "variants": variants_for(ONE, 118)},
        ],
    )
    add_product(
        db,
        name="Seef Weekend Tote",
        description=(
            "Cut a little slouchier than the Carryall, this tote is made for market mornings "
            "and late coffees in Seef. Unlined canvas-feel leather keeps it light without looking casual."
        ),
        category=totes,
        images=[CARRYALL_LOOK, CARRYALL_WORN],
        colors=[
            {"name": "Ivory", "hex": "#F0E4CB", "variants": variants_for(ONE, 92, sale_sizes={"One Size": 74})},
            {"name": "Stone", "hex": "#948A72", "variants": variants_for(ONE, 92)},
        ],
    )
    add_product(
        db,
        name="Adliya Shopper",
        description=(
            "A tall shopper with a clean silhouette and hidden magnetic close. "
            "Designed to sit upright beside a café chair and still hold a change of flats."
        ),
        category=totes,
        images=[CARRYALL_WORN],
        colors=[{"name": "Navy", "hex": "#1B2838", "variants": variants_for(ONE, 88)}],
    )
    add_product(
        db,
        name="Muharraq Market Bag",
        description=(
            "Smaller than it looks in the photograph — a compact tote for evenings when "
            "you only need keys, a card case, and a silk. The hardware is brushed, not shiny."
        ),
        category=totes,
        images=[CARRYALL_LOOK],
        colors=[
            {"name": "Burgundy", "hex": "#5C1A22", "variants": variants_for(ONE, 79, sale_sizes={"One Size": 64})},
        ],
    )

    # --- Shoulder bags ---
    add_product(
        db,
        name="Speedy Bandoulière 25",
        description=(
            "The compact shoulder bag we reach for from Thursday dinner to Friday prayer. "
            "Detachable strap, zip top, and enough structure to stand on a restaurant table."
        ),
        category=shoulder,
        images=[SPEEDY],
        colors=[
            {"name": "Monogram Sand", "hex": "#C9C0AC", "variants": variants_for(ONE, 105)},
            {"name": "Black", "hex": "#131210", "variants": variants_for(ONE, 105, sale_sizes={"One Size": 89})},
        ],
    )
    add_product(
        db,
        name="Riffa Crossbody",
        description=(
            "A slightly longer strap and a slimmer body, made for hands-free walking through Riffa souq. "
            "The leather softens after a week of wear."
        ),
        category=shoulder,
        images=[SPEEDY],
        colors=[{"name": "Stone", "hex": "#948A72", "variants": variants_for(ONE, 74, sale_sizes={"One Size": 59})}],
    )
    add_product(
        db,
        name="Amwaj Mini Shoulder",
        description=(
            "Evening-small without being a clutch. Holds a phone, lipstick, and a folded invitation. "
            "The hardware is quiet gold — no logo shouting from across the room."
        ),
        category=shoulder,
        images=[SPEEDY],
        colors=[
            {"name": "Ivory", "hex": "#F0E4CB", "variants": variants_for(ONE, 68)},
            {"name": "Burgundy", "hex": "#5C1A22", "variants": variants_for(ONE, 68)},
        ],
    )
    add_product(
        db,
        name="Juffair Day Bag",
        description=(
            "A practical mid-size with an interior slip pocket for a boarding pass. "
            "Works with an abaya or a knit set — the shape stays neat when full."
        ),
        category=shoulder,
        images=[SPEEDY],
        colors=[{"name": "Navy", "hex": "#1B2838", "variants": variants_for(ONE, 82)}],
    )

    # --- Heels ---
    add_product(
        db,
        name="Luna Pump",
        description=(
            "A refined pointed pump with a wearable mid heel — made for long wedding halls "
            "and marble hotel floors. The leather is softly padded at the toe."
        ),
        category=heels,
        images=[PUMP_WORN, PUMP_CROP],
        colors=[
            {
                "name": "Sand",
                "hex": "#C9C0AC",
                "variants": variants_for(SHOES, 98, zero=("36",), low=("40",), sale_sizes={"38": 79}),
            },
            {"name": "Black", "hex": "#131210", "variants": variants_for(SHOES, 98, zero=("40",), low=("36",))},
        ],
    )
    add_product(
        db,
        name="Hidd Salon Heel",
        description=(
            "A slightly higher Luna last with a slimmer throat. Best with cropped trousers "
            "or a midi dress — the toe is sharp without looking severe."
        ),
        category=heels,
        images=[PUMP_CROP, PUMP_WORN],
        colors=[{"name": "Ivory", "hex": "#F0E4CB", "variants": variants_for(SHOES, 108, zero=("39",), low=("36", "40"), sale_sizes={"38": 88})}],
    )
    add_product(
        db,
        name="Dilmun Court Shoe",
        description=(
            "A closed court shoe in a darker stone, meant for office days that become dinners. "
            "The heel is stacked and stable on Bahrain's older pavements."
        ),
        category=heels,
        images=[PUMP_WORN],
        colors=[
            {"name": "Stone", "hex": "#948A72", "variants": variants_for(SHOES, 86, zero=("37",))},
            {"name": "Burgundy", "hex": "#5C1A22", "variants": variants_for(SHOES, 86, low=("40",), sale_sizes={"37": 69})},
        ],
    )
    add_product(
        db,
        name="Gudaibiya Evening Pump",
        description=(
            "The dressiest of the set — a deeper last and a quieter shine. "
            "Pair with a floor-length dress; the heel height is designed for sitting and standing in equal measure."
        ),
        category=heels,
        images=[PUMP_CROP],
        colors=[{"name": "Navy", "hex": "#1B2838", "variants": variants_for(SHOES, 112, zero=("36", "40"), low=("39",))}],
    )

    # --- Knitwear ---
    add_product(
        db,
        name="Half-Zip Rib Pullover",
        description=(
            "A fine rib knit with a half zip that sits cleanly under an abaya or on its own. "
            "The wool-blend yarn holds its shape in air-conditioned rooms without itching."
        ),
        category=knitwear,
        images=[PULLOVER],
        colors=[
            {
                "name": "Camel",
                "hex": "#C4A574",
                "variants": variants_for(CLOTHING, 48, zero=("XS",), low=("XL",), sale_sizes={"M": 38}),
            },
            {"name": "Black", "hex": "#131210", "variants": variants_for(CLOTHING, 48, zero=("XL",), low=("XS",))},
        ],
    )
    add_product(
        db,
        name="Woven-Effect Knit Skirt",
        description=(
            "A midi knit skirt with a woven surface that reads as texture, not pattern. "
            "The elastic waist sits flat; the hem is weighted so it doesn't cling in the wind."
        ),
        category=knitwear,
        images=[SKIRT],
        colors=[
            {"name": "Stone", "hex": "#948A72", "variants": variants_for(CLOTHING, 42, zero=("S",), low=("XS",))},
            {"name": "Ivory", "hex": "#F0E4CB", "variants": variants_for(CLOTHING, 42, sale_sizes={"L": 34})},
        ],
    )
    add_product(
        db,
        name="Sitra Knit Set Top",
        description=(
            "The pullover cut a touch shorter, meant to tuck into the woven skirt. "
            "Same rib, same half zip — wear them together or split the set across the week."
        ),
        category=knitwear,
        images=[PULLOVER],
        colors=[{"name": "Sand", "hex": "#C9C0AC", "variants": variants_for(CLOTHING, 44, zero=("L",), low=("XS",))}],
    )
    add_product(
        db,
        name="Budaiya Column Skirt",
        description=(
            "A straighter knit skirt than the woven-effect, falling closer to the ankle. "
            "Works under a light abaya or with the half-zip for a covered, modern line."
        ),
        category=knitwear,
        images=[SKIRT],
        colors=[{"name": "Navy", "hex": "#1B2838", "variants": variants_for(CLOTHING, 46, zero=("XL",), sale_sizes={"M": 37})}],
    )
    add_product(
        db,
        name="A'ali Weekend Knit",
        description=(
            "A softer, slightly oversized take on the rib pullover. "
            "The zip is optional — wear it closed at the office or open over a silk."
        ),
        category=knitwear,
        images=[PULLOVER],
        colors=[
            {"name": "Burgundy", "hex": "#5C1A22", "variants": variants_for(CLOTHING, 52, low=("XS", "XL"), sale_sizes={"S": 41})},
        ],
    )

    # --- Outerwear ---
    add_product(
        db,
        name="Scarf-Detail Bomber",
        description=(
            "A light bomber with a scarf-tied neckline — the piece you throw on when "
            "the evening drops after a late dinner. The fabric is wind-resistant without looking sporty."
        ),
        category=outerwear,
        images=[BOMBER],
        colors=[
            {"name": "Black", "hex": "#131210", "variants": variants_for(CLOTHING, 78, zero=("XS",), low=("XL",))},
            {"name": "Stone", "hex": "#948A72", "variants": variants_for(CLOTHING, 78, sale_sizes={"M": 62})},
        ],
    )
    add_product(
        db,
        name="Hooded Monogram Denim Jacket",
        description=(
            "A hooded denim jacket with a quiet monogram wash. Structured through the shoulder, "
            "easy through the body — layer over a knit or a linen jalabiya."
        ),
        category=outerwear,
        images=[DENIM_JACKET],
        colors=[{"name": "Indigo", "hex": "#2C3A4F", "variants": variants_for(CLOTHING, 72, zero=("S",), low=("XS",), sale_sizes={"M": 58})}],
    )
    add_product(
        db,
        name="Zallaq Evening Bomber",
        description=(
            "The scarf bomber in a deeper black, with a slightly longer hem. "
            "Made for the car-to-door stretch on cooler desert nights."
        ),
        category=outerwear,
        images=[BOMBER],
        colors=[{"name": "Black", "hex": "#131210", "variants": variants_for(CLOTHING, 84, zero=("XL",), sale_sizes={"L": 69})}],
    )
    add_product(
        db,
        name="Saar Hooded Jacket",
        description=(
            "A lighter wash of the hooded denim, meant for daytime errands. "
            "The hood sits neatly under a shayla; the cuffs are buttoned, not elastic."
        ),
        category=outerwear,
        images=[DENIM_JACKET],
        colors=[{"name": "Washed Indigo", "hex": "#5A6B7C", "variants": variants_for(CLOTHING, 68, low=("XL",))}],
    )

    # --- Denim ---
    add_product(
        db,
        name="Monogram Mini Shorts",
        description=(
            "High-rise mini shorts in monogram denim — for private gatherings and travel days, "
            "not the office. The rise is modest; the hem is clean, not frayed."
        ),
        category=denim,
        images=[SHORTS],
        colors=[
            {"name": "Indigo", "hex": "#2C3A4F", "variants": variants_for(CLOTHING, 38, zero=("XS",), low=("XL",), sale_sizes={"M": 29})},
        ],
    )
    add_product(
        db,
        name="Amwaj Denim Short",
        description=(
            "A slightly longer short than the mini, hitting closer to mid-thigh. "
            "Same monogram denim, softer wash, with a wider belt loop for a silk tie."
        ),
        category=denim,
        images=[SHORTS],
        colors=[{"name": "Stone Wash", "hex": "#7A8490", "variants": variants_for(CLOTHING, 36, zero=("L",), low=("XS",))}],
    )
    add_product(
        db,
        name="Tubli Hooded Denim",
        description=(
            "The hooded jacket restated as a denim layer — same cut, lighter hardware. "
            "Wear open over a pullover when the mall air-conditioning is too much."
        ),
        category=denim,
        images=[DENIM_JACKET],
        colors=[{"name": "Indigo", "hex": "#2C3A4F", "variants": variants_for(CLOTHING, 70, zero=("M",))}],
    )
    add_product(
        db,
        name="Jidhafs Weekend Short",
        description=(
            "The darkest wash of the mini short. Pair with the half-zip and flats "
            "for a covered-from-the-car look that still feels like Saturday."
        ),
        category=denim,
        images=[SHORTS],
        colors=[{"name": "Black Denim", "hex": "#1A1C20", "variants": variants_for(CLOTHING, 40, low=("XS", "XL"), sale_sizes={"S": 32})}],
    )

    # --- Jewelry ---
    add_product(
        db,
        name="Iconic Drop Earrings",
        description=(
            "Sculptural drop earrings with a small monogram motif. Light enough for all-day wear, "
            "polished enough for a wedding hall. The clasp is a secure push-back."
        ),
        category=jewelry,
        images=[EARRINGS_WORN, EARRINGS_LOOK],
        colors=[
            {"name": "Gold", "hex": "#C4A45A", "variants": variants_for(ONE, 62, sale_sizes={"One Size": 49})},
            {"name": "Silver", "hex": "#C0C4C8", "variants": variants_for(ONE, 58)},
        ],
    )
    add_product(
        db,
        name="Seef Icon Studs",
        description=(
            "A quieter reading of the Iconic motif — closer to the lobe, less swing. "
            "Designed to sit cleanly against a shayla edge."
        ),
        category=jewelry,
        images=[EARRINGS_LOOK, EARRINGS_WORN],
        colors=[{"name": "Gold", "hex": "#C4A45A", "variants": variants_for(ONE, 48, sale_sizes={"One Size": 39})}],
    )
    add_product(
        db,
        name="Dilmun Hoop",
        description=(
            "A medium hoop finished in the same gold tone as the drops. "
            "Hollow construction keeps them light; the hinge clicks shut."
        ),
        category=jewelry,
        images=[EARRINGS_WORN],
        colors=[{"name": "Gold", "hex": "#C4A45A", "variants": variants_for(ONE, 54)}],
    )
    add_product(
        db,
        name="Look Earrings",
        description=(
            "The longest drop in the set — for black-tie and hotel weddings. "
            "Best with hair up or a sleek shayla so the line stays visible."
        ),
        category=jewelry,
        images=[EARRINGS_LOOK],
        colors=[
            {"name": "Gold", "hex": "#C4A45A", "variants": variants_for(ONE, 72)},
            {"name": "Silver", "hex": "#C0C4C8", "variants": variants_for(ONE, 68, sale_sizes={"One Size": 55})},
        ],
    )

    # --- Scarves ---
    add_product(
        db,
        name="June Silk Square",
        description=(
            "A silk twill square with a soft print — light enough for Bahrain humidity, "
            "opaque enough to wear as a neckerchief or a bag accent."
        ),
        category=scarves,
        images=[SILK],
        colors=[
            {"name": "Ivory Print", "hex": "#F0E4CB", "variants": variants_for(ONE, 36)},
            {"name": "Sand Print", "hex": "#C9C0AC", "variants": variants_for(ONE, 36, sale_sizes={"One Size": 28})},
        ],
    )
    add_product(
        db,
        name="Muharraq Silk",
        description=(
            "A larger square than June, meant to drape over the shoulder of a bomber or tote. "
            "The hand-roll is narrow and even."
        ),
        category=scarves,
        images=[SILK],
        colors=[{"name": "Stone Print", "hex": "#948A72", "variants": variants_for(ONE, 42, sale_sizes={"One Size": 33})}],
    )
    add_product(
        db,
        name="Reef Neck Silk",
        description=(
            "A slim silk for tying at the neck or through a bag handle. "
            "The print is quieter — more texture than motif."
        ),
        category=scarves,
        images=[SILK],
        colors=[{"name": "Navy Print", "hex": "#1B2838", "variants": variants_for(ONE, 29)}],
    )
    add_product(
        db,
        name="Evening Silk",
        description=(
            "The deepest colourway of the June silk, for black dresses and navy pumps. "
            "One side is slightly more matte so it doesn't flash under chandeliers."
        ),
        category=scarves,
        images=[SILK],
        colors=[{"name": "Burgundy Print", "hex": "#5C1A22", "variants": variants_for(ONE, 39)}],
    )

    # --- Charms ---
    add_product(
        db,
        name="Vivienne Bag Charm",
        description=(
            "A small sculptural charm that clips onto a tote or shoulder strap. "
            "Playful without being loud — a signature for the bag you carry every week."
        ),
        category=charms,
        images=[CHARM],
        colors=[
            {"name": "Gold", "hex": "#C4A45A", "variants": variants_for(ONE, 34, sale_sizes={"One Size": 26})},
            {"name": "Silver", "hex": "#C0C4C8", "variants": variants_for(ONE, 32)},
        ],
    )
    add_product(
        db,
        name="Fashionista Charm",
        description=(
            "A slightly larger charm with more movement when you walk. "
            "Clips onto the Speedy or the Carryall without scratching the leather."
        ),
        category=charms,
        images=[CHARM],
        colors=[{"name": "Gold", "hex": "#C4A45A", "variants": variants_for(ONE, 38, sale_sizes={"One Size": 30})}],
    )
    add_product(
        db,
        name="Mini Vivienne",
        description=(
            "The smallest charm in the family — for the Amwaj mini or a key ring. "
            "Same finish, quieter scale."
        ),
        category=charms,
        images=[CHARM],
        colors=[{"name": "Gold", "hex": "#C4A45A", "variants": variants_for(ONE, 28)}],
    )
    add_product(
        db,
        name="Weekend Charm",
        description=(
            "A two-tone reading of the Vivienne, meant for the denim jacket zip or a tote. "
            "The clip is spring-loaded and stays put."
        ),
        category=charms,
        images=[CHARM],
        colors=[{"name": "Two-tone", "hex": "#8A7A58", "variants": variants_for(ONE, 36)}],
    )


def main() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).count()
        customers = db.query(Customer).count()
        orders = db.query(Order).count()
        items = db.query(OrderItem).count()
        print(f"Leaving untouched — users={users}, customers={customers}, orders={orders}, order_items={items}")
        if customers or orders or items:
            print("Note: customers/orders are not empty. Catalog wipe will not delete them.")

        db.query(ProductVariant).delete()
        db.query(ProductImage).delete()
        db.query(ProductColor).delete()
        db.query(Product).delete()
        db.query(Category).filter(Category.parent_id.isnot(None)).delete()
        db.query(Category).filter(Category.parent_id.is_(None)).delete()
        db.commit()
        print("Catalog tables cleared.")

        removed = wipe_upload_dir(UPLOAD_CATS) + wipe_upload_dir(UPLOAD_PRODS)
        print(f"Removed {removed} orphaned upload file(s). Left static/img/Product/ untouched.")

        seed(db)
        db.commit()

        tops = db.query(Category).filter(Category.parent_id.is_(None)).count()
        subs = db.query(Category).filter(Category.parent_id.isnot(None)).count()
        products = db.query(Product).count()
        colors = db.query(ProductColor).count()
        variants = db.query(ProductVariant).count()
        on_sale = (
            db.query(ProductVariant)
            .filter(
                ProductVariant.compare_at_price.isnot(None),
                ProductVariant.compare_at_price < ProductVariant.price,
            )
            .count()
        )
        print(
            f"Seeded: {tops} top-level categories, {subs} subcategories, "
            f"{products} products, {colors} colors, {variants} variants "
            f"({on_sale} on sale)."
        )
        print("Re-run this script anytime to reset the catalog to this demo state.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
