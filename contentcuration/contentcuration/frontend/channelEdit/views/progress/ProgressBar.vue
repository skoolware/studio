<template>

  <!-- Show progress bar if progress is tracked -->
  <VLayout v-if="progressPercent !== null && !isDone" row align-center class="mt-3">
    <VProgressLinear
      v-model="progressPercent"
      class="ma-0"
      height="10"
      data-test="progress"
      :color="progressBarColor"
    />
    <VFlex class="text-xs-right pl-3" shrink>
      {{ $tr('progressText', {percent: Math.round(progressPercent) || '0'}) }}
    </VFlex>
  </VLayout>

</template>


<script>

  export default {
    name: 'ProgressBar',
    props: {
      progressPercent: {
        type: Number,
        default: null,
      },
      currentTaskError: {
        type: Boolean,
        default: false,
      },
    },
    computed: {
      isDone() {
        return this.progressPercent >= 100 && !this.currentTaskError;
      },
      progressBarColor() {
        if (this.currentTaskError) {
          return this.$themeTokens.error;
        } else if (this.isDone) {
          return this.$themeTokens.success;
        } else {
          return this.$themeTokens.loading;
        }
      },
    },
    $trs: {
      progressText: '{percent}%',
    },
  };

</script>
