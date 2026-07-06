<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  onMount(() => {
    goto('/dashboard');
  });
</script>

<section class="page-head">
  <p class="eyebrow">Avvio</p>
  <h2>Preparazione dashboard</h2>
</section>
