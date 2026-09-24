/**
 * VerificationBanner: spec §4.4 / §8 / §9.
 *
 * Rendered ABOVE the workspace (never inside a scroll container), so it can't
 * be scrolled away. It has no dismiss control by design: an unverified
 * placement must never look final. Status is conveyed by icon + text, not
 * colour alone (§10).
 */
import { Icon } from "../common/Icon";
import { isVerified, unavailableReason } from "../../state/selectors";
import type { Persona } from "../../state/sessionTypes";
import "./banners.css";

interface VerificationBannerProps {
  verificationStatus: string;
  persona: Persona;
  isLegalized: boolean;
  /** True when the response contradicts its own invariants (see InternalErrorBanner). */
  contradicted: boolean;
}

export function VerificationBanner({ verificationStatus, persona, isLegalized, contradicted }: VerificationBannerProps) {
  // A "verified" label that the response itself contradicts must not read as
  // a green all-clear next to the red inconsistency banner.
  if (isVerified(verificationStatus) && contradicted) {
    return (
      <div className="vbanner is-warn" role="alert">
        <Icon name="alertTriangle" size={16} />
        <p>
          <strong>Reported as verified, but not trustworthy.</strong> The same response contradicts the verification
          contract (details above). Treat this placement as unverified.
        </p>
      </div>
    );
  }
  if (isVerified(verificationStatus)) {
    return (
      <div className="vbanner is-ok" role="status">
        <Icon name="checkCircle" size={16} />
        <p>
          <strong>Verified.</strong>{" "}
          {persona === "beginner"
            ? "This placement was checked by a professional placement tool and passes its legality rules."
            : `Legalized and scored by DREAMPlace/OpenROAD${isLegalized ? " (is_legalized = true)" : ""}.`}
        </p>
      </div>
    );
  }

  // Edits can report differing before/after statuses, surface them directly (§6.3).
  const isCombined = verificationStatus.startsWith("before:");
  return (
    <div className="vbanner is-warn" role="alert">
      <Icon name="alertTriangle" size={16} />
      <p>
        <strong>Placement not verified.</strong>{" "}
        {isCombined ? (
          <>
            Verification differs between states: <code>{verificationStatus}</code>.
          </>
        ) : (
          <>
            DREAMPlace/OpenROAD unavailable ({unavailableReason(verificationStatus)}).
          </>
        )}{" "}
        Coordinates shown are unverified and may overlap or be illegal.
      </p>
    </div>
  );
}
