export const DASH = "—";

const MONEY_SUFFIXES = [
  ["T", 1e12],
  ["B", 1e9],
  ["M", 1e6],
  ["K", 1e3],
];

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function expandExponential(text) {
  const match = String(text).match(/^(-?)(\d+(?:\.\d+)?)e([+-]?\d+)$/i);
  if (!match) return text;
  const [, sign, mantissa, exponentRaw] = match;
  const exponent = Number(exponentRaw);
  const [intPart, fracPart = ""] = mantissa.split(".");
  const digits = intPart + fracPart;
  const decimalIndex = intPart.length + exponent;
  if (decimalIndex <= 0) {
    return `${sign}0.${"0".repeat(-decimalIndex)}${digits}`;
  }
  if (decimalIndex >= digits.length) {
    return `${sign}${digits}${"0".repeat(decimalIndex - digits.length)}`;
  }
  return `${sign}${digits.slice(0, decimalIndex)}.${digits.slice(decimalIndex)}`;
}

function trimZeros(text) {
  if (!text.includes(".")) return text;
  return text.replace(/0+$/, "").replace(/\.$/, "");
}

export function plainSig(value, sig = 6) {
  if (!isFiniteNumber(value)) return null;
  if (value === 0) return "0";
  const text = value.toPrecision(sig);
  return trimZeros(/e/i.test(text) ? expandExponential(text) : text);
}

function plainFixed(value, digits) {
  return trimZeros(value.toFixed(digits));
}

function groupInteger(integer) {
  const negative = integer.startsWith("-");
  const digits = negative ? integer.slice(1) : integer;
  let grouped = "";
  let rest = digits;
  while (rest.length > 3) {
    grouped = "." + rest.slice(-3) + grouped;
    rest = rest.slice(0, -3);
  }
  grouped = rest + grouped;
  return negative ? `-${grouped}` : grouped;
}

export function toTr(text) {
  if (text === null || text === undefined) return DASH;
  const raw = String(text);
  const [integer, decimal] = raw.split(".");
  const grouped = groupInteger(integer);
  return decimal ? `${grouped},${decimal}` : grouped;
}

export function num(value, sig = 6) {
  const text = plainSig(value, sig);
  return text === null ? DASH : toTr(text);
}

export function price(value, currency = "$") {
  if (!isFiniteNumber(value)) return DASH;
  const abs = Math.abs(value);
  let text;
  if (abs >= 1000) text = plainFixed(value, 2);
  else if (abs >= 1) text = plainSig(value, 5);
  else text = plainSig(value, 4);
  return `${currency}${toTr(text)}`;
}

export function money(value, { exact = false, currency = "$" } = {}) {
  if (!isFiniteNumber(value)) return DASH;
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (exact || abs < 1000) {
    const text = exact && abs >= 1 ? plainFixed(abs, 2) : plainSig(abs, 4);
    return `${sign}${currency}${toTr(text)}`;
  }
  for (const [suffix, factor] of MONEY_SUFFIXES) {
    if (abs >= factor) {
      const scaled = abs / factor;
      const digits = scaled < 10 ? 2 : 1;
      return `${sign}${currency}${toTr(plainFixed(scaled, digits))}${suffix}`;
    }
  }
  return `${sign}${currency}${toTr(plainSig(abs, 4))}`;
}

export function pct(value, { signed = false, digits = 1, cap = 9999 } = {}) {
  if (!isFiniteNumber(value)) return DASH;
  if (Math.abs(value) > cap) {
    const capText = toTr(String(Math.trunc(cap)));
    return `>${value < 0 ? "-" : ""}%${capText}`;
  }
  const text = Math.abs(value).toFixed(digits).replace(".", ",");
  const sign = value < 0 ? "-" : signed ? "+" : "";
  return `${sign}%${text}`;
}

export function ratio(value) {
  if (!isFiniteNumber(value)) return DASH;
  return `×${num(value, 3)} (${pct((value - 1) * 100, { signed: true })})`;
}

export function score(value, digits = 2) {
  if (!isFiniteNumber(value)) return DASH;
  const text = Math.abs(value).toFixed(digits).replace(".", ",");
  return `${value < 0 ? "-" : "+"}${text}`;
}

export function priceRange(low, high, currency = "$") {
  if (!isFiniteNumber(low) || !isFiniteNumber(high)) return DASH;
  return `${price(low, currency)} – ${price(high, currency)}`;
}

export function formatDateTime(value) {
  if (!value) return DASH;
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return DASH;
  return date.toLocaleString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatAxisDate(value, timeframe = "1d") {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  if (["15m", "30m", "1h", "4h"].includes(timeframe)) {
    return date.toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "2-digit" });
}
