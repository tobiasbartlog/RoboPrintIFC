import { createContext, useContext } from 'react';

export type View = 'flow' | 'pattern';

/** Ansichtswechsel (Ablauf ↔ Musterersteller) für Knöpfe, die von einer Ansicht in die andere führen. */
export const ViewContext = createContext<(view: View) => void>(() => {});

export const useSetView = () => useContext(ViewContext);
