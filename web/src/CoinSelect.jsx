import { useEffect, useId, useRef, useState } from "react";

export default function CoinSelect({
  defaultValue = "",
  placeholder,
  onManualChange,
  onSelect,
  onSubmit,
}) {
  const [text, setText] = useState(defaultValue);
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const wrapperRef = useRef(null);
  const debounceRef = useRef(null);
  const requestRef = useRef(0);
  const suggestionsId = useId();

  useEffect(() => {
    const handleOutside = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  useEffect(() => () => debounceRef.current && clearTimeout(debounceRef.current), []);

  const runSearch = (value) => {
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    setLoading(true);
    fetch(`/api/coins/search?q=${encodeURIComponent(value)}&limit=8`)
      .then((response) => (response.ok ? response.json() : { results: [] }))
      .then((data) => {
        if (requestId !== requestRef.current) return;
        const list = data.results || [];
        setResults(list);
        setOpen(true);
        setHighlight(list.length ? 0 : -1);
      })
      .catch(() => {
        if (requestId !== requestRef.current) return;
        setResults([]);
        setOpen(true);
      })
      .finally(() => {
        if (requestId === requestRef.current) setLoading(false);
      });
  };

  const handleChange = (event) => {
    const value = event.target.value;
    setText(value);
    onManualChange?.(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(() => runSearch(value.trim()), 250);
  };

  const choose = (coin) => {
    setText(`${coin.name} (${coin.symbol})`);
    setOpen(false);
    setHighlight(-1);
    onSelect?.(coin);
  };

  const handleKeyDown = (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open && results.length) setOpen(true);
      setHighlight((current) => Math.min(current + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (open && highlight >= 0 && results[highlight]) choose(results[highlight]);
      else {
        setOpen(false);
        onSubmit?.(text);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="coin-select" ref={wrapperRef}>
      <input
        className="coin-input"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        aria-controls={suggestionsId}
        autoComplete="off"
        value={text}
        placeholder={placeholder}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={(event) => {
          event.target.select();
          if (results.length) setOpen(true);
        }}
      />
      {open && (
        <ul className="coin-dropdown" id={suggestionsId} role="listbox">
          {loading && <li className="coin-empty">Aranıyor…</li>}
          {!loading && results.length === 0 && (
            <li className="coin-empty">Sonuç bulunamadı; tam kimlik yazıp Enter'a basabilirsiniz.</li>
          )}
          {!loading &&
            results.map((coin, index) => (
              <li
                key={coin.id}
                id={`${suggestionsId}-option-${index}`}
                role="option"
                aria-selected={index === highlight}
                className={`coin-option ${index === highlight ? "active" : ""}`}
                onMouseEnter={() => setHighlight(index)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(coin)}
              >
                <span className="coin-symbol">{coin.symbol}</span>
                <span className="coin-name">{coin.name}</span>
                <span className="coin-rank">{coin.rank ? `#${coin.rank}` : ""}</span>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
