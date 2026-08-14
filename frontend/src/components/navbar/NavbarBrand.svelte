<script lang="ts">
  import { t } from '$stores/locale';

  // Import logo asset for proper Vite processing
  import logoBanner from '../../assets/logo-banner.png';
</script>

<!-- Far Left: logo (nieklikalne — "O programie" jest w menu użytkownika) -->
<div class="navbar-brand">
  <img src={logoBanner} alt={$t('nav.logoAlt')} class="logo-banner" />
</div>

<style>
  .navbar-brand {
    display: flex;
    align-items: center;
  }

  .logo-banner {
    height: 36px;
    width: auto;
    object-fit: contain;
    border-radius: 6px;
    transition: inherit;
  }

  /* iPad portrait — smaller logo */
  @media (max-width: 1024px) {
    .logo-banner {
      height: 30px;
    }
  }

  @media (max-width: 768px) {
    .logo-banner {
      height: 28px;
    }
  }

  /* Extra-small screens (iPhone SE, 375px and below) */
  @media (max-width: 480px) {
    .logo-banner {
      height: 24px;
    }
  }
</style>
