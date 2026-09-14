import { useEffect, useMemo, useRef, useState } from "react";
import { IconSearch } from "./icons.jsx";

export default function CommandPalette({ open, onClose, commands, onSearchCoins, onPickCoin }) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const [coins, setCoins] = useState([]);
  const [coinLoading, setCoinLoading] = useState(false);
  const inputRef = useRef(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setIndex(0);
    setCoins([]);
    setTimeout(() => inputRef.current?.focus(), 10);
  }, [open]);

  useEffect(() => {
    if (!open || !onSearchCoins) return undefined;
    const value = query.trim();
    if (value.length < 2 || value.includes(":")) {
      setCoins([]);
      return undefined;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setCoinLoading(true);
      try {
        setCoins((await onSearchCoins(value)) || []);
      } catch {
        setCoins([]);
      } finally {
        setCoinLoading(false);
      }
    }, 250);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  }, [query, open, onSearchCoins]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands.slice(0, 10);
    return commands
      .filter(
        (command) =>
          command.label.toLowerCase().includes(needle) ||
          (command.keywords || "").toLowerCase().includes(needle)
      )
      .slice(0, 10);
  }, [commands, query]);

  const items = useMemo(
    () => [
      ...coins.map((suggestion) => ({
        id: `coin:${suggestion.id}`,
        label: `Varlık: ${suggestion.name} (${suggestion.symbol})`,
        group: "Varlık",
        run: () => onPickCoin(suggestion),
      })),
      ...filtered,
    ],
    [coins, filtered, onPickCoin]
  );

  useEffect(() => {
    setIndex(0);
  }, [items.length]);

  if (!open) return null;

  const execute = (item) => {
    if (!item) return;
    item.run();
    onClose();
  };

  return (
    <div className="palette-backdrop" onClick={onClose} role="presentation">
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Komut paleti"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="palette-input">
          <IconSearch width={14} height={14} />
          <input
            ref={inputRef}
            value={query}
            placeholder="Komut veya varlık yazın… (ör. genel bakış, analiz çalıştır, btc, modül)"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setIndex((current) => Math.min(current + 1, items.length - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setIndex((current) => Math.max(current - 1, 0));
              } else if (event.key === "Enter") {
                event.preventDefault();
                execute(items[index]);
              } else if (event.key === "Escape") {
                event.preventDefault();
                onClose();
              }
            }}
          />
          {coinLoading && <span className="spinner" />}
        </div>
        <ul className="palette-list" role="listbox">
          {items.length === 0 && <li className="palette-empty">Sonuç yok</li>}
          {items.map((item, itemIndex) => (
            <li
              key={item.id}
              role="option"
              aria-selected={itemIndex === index}
              className={`palette-item ${itemIndex === index ? "active" : ""}`}
              onMouseEnter={() => setIndex(itemIndex)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => execute(item)}
            >
              <span>{item.label}</span>
              {item.group && <span className="palette-group">{item.group}</span>}
            </li>
          ))}
        </ul>
        <div className="palette-foot">
          <span className="muted small">↑↓ gez · ↵ çalıştır · Esc kapat</span>
          <kbd>⌘K</kbd>
        </div>
      </div>
    </div>
  );
}
