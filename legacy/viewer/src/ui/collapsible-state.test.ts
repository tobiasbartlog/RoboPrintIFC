import { describe, expect, it } from "vitest";

import {
  type CollapsibleState,
  collapsibleState,
  collapsibleView,
  setCollapsible,
  toggleCollapsible,
} from "./collapsible-state";

describe("collapsible aufklapp-state (Scheibe 2b, Issue #60)", () => {
  it("Default ist zugeklappt", () => {
    expect(collapsibleState()).toEqual({ expanded: false });
  });

  it("startet auf Wunsch aufgeklappt", () => {
    expect(collapsibleState(true)).toEqual({ expanded: true });
  });

  it("toggle kippt den Zustand hin und zurück", () => {
    const zu = collapsibleState();
    const auf = toggleCollapsible(zu);
    expect(auf).toEqual({ expanded: true });
    expect(toggleCollapsible(auf)).toEqual({ expanded: false });
  });

  it("toggle mutiert den Eingangszustand nicht (rein)", () => {
    const zu: CollapsibleState = collapsibleState();
    toggleCollapsible(zu);
    expect(zu).toEqual({ expanded: false });
  });

  it("setCollapsible setzt explizit", () => {
    expect(setCollapsible(true)).toEqual({ expanded: true });
    expect(setCollapsible(false)).toEqual({ expanded: false });
  });

  it("view: zugeklappt versteckt den Körper und meldet aria-expanded=false", () => {
    const view = collapsibleView(collapsibleState(false), "Fortgeschritten");
    expect(view.bodyHidden).toBe(true);
    expect(view.ariaExpanded).toBe("false");
    expect(view.toggleLabel).toBe("▸ Fortgeschritten");
  });

  it("view: aufgeklappt zeigt den Körper und meldet aria-expanded=true", () => {
    const view = collapsibleView(collapsibleState(true), "Fortgeschritten");
    expect(view.bodyHidden).toBe(false);
    expect(view.ariaExpanded).toBe("true");
    expect(view.toggleLabel).toBe("▾ Fortgeschritten");
  });
});
