import { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import api from "@/lib/api";

const PrivacyModeContext = createContext(null);

const UNLOCK_DURATION_MS = 15 * 60 * 1000; // auto-relock after 15 minutes

export function PrivacyModeProvider({ children }) {
  const [isCashHidden, setIsCashHidden] = useState(true);
  const [showPinModal, setShowPinModal] = useState(false);
  const relockTimer = useRef(null);

  const relock = useCallback(() => {
    setIsCashHidden(true);
    clearTimeout(relockTimer.current);
  }, []);

  useEffect(() => () => clearTimeout(relockTimer.current), []);

  const requestUnlock = () => setShowPinModal(true);

  const unlockWithPin = async (pin) => {
    await api.post("/finance/verify-privacy-pin", { pin }); // throws on wrong/unset PIN — modal surfaces the error
    setIsCashHidden(false);
    setShowPinModal(false);
    clearTimeout(relockTimer.current);
    relockTimer.current = setTimeout(relock, UNLOCK_DURATION_MS);
  };

  return (
    <PrivacyModeContext.Provider value={{ isCashHidden, requestUnlock, relock, showPinModal, setShowPinModal, unlockWithPin }}>
      {children}
    </PrivacyModeContext.Provider>
  );
}

export function usePrivacyMode() {
  return useContext(PrivacyModeContext) || {
    isCashHidden: true, requestUnlock: () => {}, relock: () => {},
    showPinModal: false, setShowPinModal: () => {}, unlockWithPin: async () => {},
  };
}
