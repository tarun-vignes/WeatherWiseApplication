"use client";

import { useEffect } from "react";

export default function AboutModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal card" role="dialog" aria-modal="true" aria-labelledby="about-title" onClick={(e) => e.stopPropagation()}>
        <h3 id="about-title">About Product Manager Accelerator</h3>
        <p>
          Product Manager Accelerator (PM Accelerator) is a program where AI engineers, data scientists, designers and
          product managers work together to build real AI-powered products from scratch, with mentorship from industry
          leaders. Participants take products from idea to a working MVP and demo, building practical experience and
          portfolio work along the way.
        </p>
        <p>
          Learn more at{" "}
          <a href="https://www.pmaccelerator.io/" target="_blank" rel="noreferrer">
            pmaccelerator.io
          </a>{" "}
          and on their{" "}
          <a href="https://www.linkedin.com/school/pmaccelerator/" target="_blank" rel="noreferrer">
            LinkedIn page
          </a>
          .
        </p>
        <button className="btn primary" onClick={onClose} autoFocus>
          Close
        </button>
      </div>
    </div>
  );
}
