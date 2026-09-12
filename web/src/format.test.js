import { describe, expect, it } from "vitest";
import { DASH, money, num, pct, price, priceRange, ratio, score, toTr } from "./format.js";

describe("format", () => {
  it("tr-TR ayraclari", () => {
    expect(toTr("1234567.89")).toBe("1.234.567,89");
    expect(toTr("1234")).toBe("1.234");
    expect(toTr("0.00000331")).toBe("0,00000331");
  });

  it("mikro fiyat bilimsel gosterime dusmez", () => {
    const text = price(0.0000033123);
    expect(text.startsWith("$0,00000331")).toBe(true);
    expect(text.toLowerCase()).not.toContain("e");
    expect(price(77278)).toBe("$77.278");
    expect(price(2516.26)).toBe("$2.516,26");
  });

  it("None/NaN guvenli", () => {
    expect(price(null)).toBe(DASH);
    expect(price(Number.NaN)).toBe(DASH);
    expect(price(0)).toBe("$0");
  });

  it("buyuk tutarlar kisaltilir", () => {
    expect(money(303034652)).toBe("$303M");
    expect(money(1_551_982_234_870)).toBe("$1,55T");
    expect(money(223017, { exact: true })).toBe("$223.017");
  });

  it("yuzde isaret ve sinir", () => {
    expect(pct(23.56, { signed: true })).toBe("+%23,6");
    expect(pct(-38.7)).toBe("-%38,7");
    expect(pct(113862.5)).toBe(">%9.999");
    expect(pct(null)).toBe(DASH);
  });

  it("oran ve skor", () => {
    expect(ratio(1.236)).toBe("×1,24 (+%23,6)");
    expect(score(0.2273)).toBe("+0,23");
    expect(score(null)).toBe(DASH);
  });

  it("sayi bilimsel gosterim uretmez", () => {
    expect(num(3.31e-6)).toBe("0,00000331");
    expect(num(1.2273286800148754e-7).toLowerCase()).not.toContain("e");
  });

  it("aralik bicimi", () => {
    const text = priceRange(0.00000303, 0.00000359);
    expect(text).toContain("$0,00000303");
    expect(text).toContain("$0,00000359");
    expect(text.toLowerCase()).not.toContain("e");
  });
});
