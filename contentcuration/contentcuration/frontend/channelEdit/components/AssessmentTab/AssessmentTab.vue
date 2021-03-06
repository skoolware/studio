<template>

  <div>
    <VAlert
      :value="!areAssessmentItemsValid"
      icon="error"
      type="error"
      outline
      data-test="alert"
    >
      <span class="red--text font-weight-bold">{{ invalidItemsErrorMessage }}</span>
    </VAlert>

    <AssessmentEditor
      ref="assessmentEditor"
      :nodeId="nodeId"
      :items="assessmentItems"
      :itemsErrors="assessmentItemsErrors"
      :openDialog="openDialog"
      @addItem="onAddAssessmentItem"
      @updateItem="onUpdateAssessmentItem"
      @deleteItem="onDeleteAssessmentItem"
    />

    <MessageDialog
      v-model="dialog.open"
      :header="dialog.title"
      :text="dialog.message"
    >
      <template #buttons>
        <VBtn
          flat
          @click="dialog.onCancel"
        >
          {{ dialog.cancelLabel || $tr('dialogCancelBtnLabel') }}
        </VBtn>

        <VBtn
          color="primary"
          @click="dialog.onSubmit"
        >
          {{ dialog.submitLabel || $tr('dialogSubmitBtnLabel') }}
        </VBtn>
      </template>
    </MessageDialog>
  </div>

</template>

<script>

  import { mapGetters, mapActions } from 'vuex';

  import AssessmentEditor from '../AssessmentEditor/AssessmentEditor';
  import { isNodeComplete } from 'shared/utils/validation';

  import MessageDialog from 'shared/views/MessageDialog';

  export default {
    name: 'AssessmentTab',
    components: {
      AssessmentEditor,
      MessageDialog,
    },
    props: {
      nodeId: {
        type: String,
        required: true,
      },
    },
    data() {
      return {
        dialog: {
          open: false,
          title: '',
          message: '',
          cancelLabel: '',
          submitLabel: '',
          onCancel: () => {},
          onSubmit: () => {},
        },
      };
    },
    computed: {
      ...mapGetters('contentNode', ['getContentNode']),
      ...mapGetters('assessmentItem', [
        'getAssessmentItems',
        'getAssessmentItemsErrors',
        'getAssessmentItemsAreValid',
        'getInvalidAssessmentItemsCount',
      ]),
      assessmentItems() {
        return this.getAssessmentItems(this.nodeId);
      },
      areAssessmentItemsValid() {
        return this.getAssessmentItemsAreValid({ contentNodeId: this.nodeId, ignoreNew: true });
      },
      assessmentItemsErrors() {
        return this.getAssessmentItemsErrors({ contentNodeId: this.nodeId, ignoreNew: true });
      },
      invalidItemsErrorMessage() {
        const invalidItemsCount = this.getInvalidAssessmentItemsCount({
          contentNodeId: this.nodeId,
          ignoreNew: true,
        });

        if (!invalidItemsCount) {
          return '';
        }

        return this.$tr('incompleteItemsCountMessage', { invalidItemsCount });
      },
    },
    watch: {
      assessmentItems(newAssessmentItems) {
        const nodeDetails = this.getContentNode(this.nodeId);
        const complete = isNodeComplete({ nodeDetails, assessmentItems: newAssessmentItems });
        this.updateContentNode({ id: this.nodeId, complete });
      },
    },
    methods: {
      ...mapActions('contentNode', ['updateContentNode']),
      ...mapActions('assessmentItem', [
        'addAssessmentItem',
        'updateAssessmentItem',
        'deleteAssessmentItem',
      ]),
      onAddAssessmentItem(item) {
        this.addAssessmentItem(item);
      },
      onUpdateAssessmentItem(item) {
        this.updateAssessmentItem(item);
      },
      onDeleteAssessmentItem(item) {
        this.deleteAssessmentItem(item);
      },
      openDialog({
        title = '',
        message = '',
        cancelLabel = '',
        submitLabel = '',
        onCancel = () => {},
        onSubmit = () => {},
      } = {}) {
        this.dialog = {
          open: true,
          title,
          message,
          cancelLabel,
          submitLabel,
          onCancel: () => {
            if (typeof onCancel === 'function') {
              onCancel();
            }
            this.closeDialog();
          },
          onSubmit: () => {
            if (typeof onSubmit === 'function') {
              onSubmit();
            }
            this.closeDialog();
          },
        };
      },
      closeDialog() {
        this.dialog = {
          open: false,
          title: '',
          message: '',
          cancelLabel: '',
          submitLabel: '',
          onCancel: () => {},
          onSubmit: () => {},
        };
      },
    },
    $trs: {
      incompleteItemsCountMessage:
        '{invalidItemsCount} incomplete {invalidItemsCount, plural, one {question} other {questions}}',
      dialogSubmitBtnLabel: 'Submit',
      dialogCancelBtnLabel: 'Cancel',
    },
  };

</script>
